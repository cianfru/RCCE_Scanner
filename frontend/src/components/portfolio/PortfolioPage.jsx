// Portfolio v2 (docs: the final spec). Title row, risk strip, since row, checks, the board with its
// inline detail, performance and activity. Everything Hyperliquid is read from the browser
// (usePortfolioFeeds); the scanner's per-coin context and events come from /api/portfolio/*.
// Close and cancel go through tradeActions.js, unchanged from TradingPanel.jsx.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useWallet } from "../../WalletContext.jsx";
import useViewport from "../../hooks/useViewport.js";
import useSetupMap from "../../hooks/useSetupMap.js";
import useWebSocket from "../../hooks/useWebSocket.js";
import * as hlClient from "../../services/hlClient.js";
import { apiFetch } from "../../edge.js";
import { pollWhileVisible } from "../../utils/visiblePoll.js";
import { watchToast } from "../../utils/setupMap.js";
import { Skeleton } from "../Skeleton.jsx";
import RadarSheet from "../radar/RadarSheet.jsx";
import { computeTotals, positionsOf } from "../../utils/portfolio/totals.js";
import { buildRow, countChecks, sortRows, filterRows, quietNoStop, CHECK_KEYS, CTX_CHECKS, URL_KEYS } from "../../utils/portfolio/checks.js";
import { classifyFills, roundTrips } from "../../utils/portfolio/fillTrips.js";
import { readSlots, writeCurrent, buildSnapshot, sinceChanges, sinceSummary } from "../../utils/portfolio/since.js";
import { spotNames, displayName } from "../../utils/portfolio/displayNames.js";
import { usd, age as fmtAge } from "../../utils/portfolio/format.js";
import { kKey } from "../../utils/tickerRenames.js";
import usePortfolioFeeds from "./usePortfolioFeeds.js";
import TitleRow, { STALE_HARD_MS, STALE_SOFT_MS } from "./TitleRow.jsx";
import RiskStrip from "./RiskStrip.jsx";
import SinceRow from "./SinceRow.jsx";
import ChecksRow, { SortRow } from "./ChecksRow.jsx";
import Board, { ActionNotice } from "./Board.jsx";
import BoardRow, { PhoneCard, Actions } from "./BoardRow.jsx";
import PositionDetail from "./PositionDetail.jsx";
import CloseConfirm, { CloseBody } from "./CloseConfirm.jsx";
import Performance from "./Performance.jsx";
import ActivityTabs from "./ActivityTabs.jsx";
import { makeTradeActions, closeArgs, PF_CONFIRM_SHEET } from "./tradeActions.js";
import { CoinName, pnlClass } from "./parts.jsx";
import { useHeldAssetCtx } from "./assetCtx.js";
import PageTitle from "../PageTitle.jsx";
import { CONNECT, IDENTITY, ROWS, FEEDS, TITLE } from "./copy.js";

const KEY_OF_URL = Object.fromEntries(Object.entries(URL_KEYS).map(([k, v]) => [v, k]));
const VENUE_FEEDS = new Set(["main", "xyz", "other", "spot", "earn", "staking", "vaults"]);

// The scanner's context and events for the coins held: one GET each, again after each scan (the
// shared scan-updated notice) or every 5 minutes while visible, with If-None-Match.
function useReflex(coinsKey) {
  const [ctx, setCtx] = useState(null);
  const [ev, setEv] = useState(null);
  const [failed, setFailed] = useState({});
  const tags = useRef({});
  const { scanUpdated } = useWebSocket();
  const get = useCallback(async (kind, set) => {
    if (!coinsKey) return;
    const key = `${kind}|${coinsKey}`;
    try {
      const res = await apiFetch(`/api/portfolio/${kind}?coins=${encodeURIComponent(coinsKey)}`, tags.current[key] ? { headers: { "If-None-Match": tags.current[key] } } : undefined);
      if (res.status === 304) { setFailed(f => ({ ...f, [kind]: false })); return; }
      if (!res.ok) throw new Error(String(res.status));
      tags.current[key] = res.headers.get("ETag") || undefined;
      set(await res.json());
      setFailed(f => ({ ...f, [kind]: false }));
    } catch { setFailed(f => ({ ...f, [kind]: true })); }
  }, [coinsKey]);
  const load = useCallback(() => { get("context", setCtx); }, [get]);
  useEffect(() => {
    load(); get("events", setEv);
    return pollWhileVisible(load, 300_000);
  }, [load, get]);
  useEffect(() => { if (scanUpdated) { load(); get("events", setEv); } }, [scanUpdated]); // eslint-disable-line react-hooks/exhaustive-deps
  return { ctx, ev, failed: !!(failed.context || failed.events), ctxFailed: !!failed.context, retry: () => { load(); get("events", setEv); } };
}

// What the scanner and the book looked like 24 hours ago, as a baseline snapshot (Since: 24H).
function base24h(rows, ev, trips, fills, nowMs) {
  const t = nowMs - 86400_000, ts = t / 1000;
  const coins = {};
  for (const r of rows) {
    const trip = trips.open[r.coin];
    if (trip?.openedAt && trip.openedAt > ts) continue;            // opened inside the 24 hours
    const e = ev?.coins?.[r.coin];
    let h4 = e?.at_start?.h4?.signal ?? null, d1 = e?.at_start?.d1?.signal ?? null, reg = e?.at_start?.h4?.regime ?? null;
    for (const x of e?.events || []) {
      if (x.t > ts) break;
      if (x.kind === "signal") { if (x.tf === "4h") h4 = x.to; else d1 = x.to; } else if (x.tf === "4h") reg = x.to;
    }
    const tr = r.ctx?.traders;
    coins[r.coin] = { side: r.side, h4: e ? h4 : null, d1: e ? d1 : null, reg4h: e ? reg : null, heat: null, band: null,
      tl: tr?.long?.n_day_ago ?? null, ts: tr?.short?.n_day_ago ?? null, mark: null, liqPct: null, liqAtr: null };
  }
  for (const c of trips.closed) if (c.closedAt > ts && !coins[c.coin]) coins[c.coin] = { side: c.side };
  return { v: 1, t, coins, upnl: null, equity: null };
}

function NoWallet({ connect, walletError, setViewAddress }) {
  const [draft, setDraft] = useState("");
  const [bad, setBad] = useState(false);
  const submit = e => {
    e.preventDefault();
    const ok = setViewAddress(draft.trim());
    setBad(!ok || !draft.trim());
    if (ok && draft.trim()) setDraft("");
  };
  return <div className="pf-nowallet">
    <div className="pf-title"><PageTitle>{TITLE}</PageTitle></div>
    <div className="pf-ghost" aria-hidden="true">
      <div className="pf-strip pf-ghost-strip">{[0, 1, 2, 3].map(i => <div key={i} className="pf-cell"><i className="pf-g-l" /><i className="pf-g-h" /><i className="pf-g-v" /></div>)}</div>
      {[0, 1, 2, 3].map(i => <div key={i} className="pf-ghost-row"><i className="pf-g-c" /><svg width="100%" height="44"><line x1="0" x2="100%" y1="22" y2="22" />
        <rect x={`${30 + i * 12}%`} y="17" width="9%" height="10" /><circle cx={`${52 + i * 6}%`} cy="22" r="3.5" /><rect x={`${62 + i * 4}%`} y="14" width="2" height="16" /></svg></div>)}
    </div>
    <div className="pf-connect2"><div className="pf-connect-card">
      <div className="pf-connect-t">{CONNECT.prompt}</div>
      <button type="button" onClick={connect} className="terminal-status pf-connect-btn">{CONNECT.connect}</button>
      {walletError && <div className="pf-view-error">{walletError}</div>}
      <form className="pf-view-form" onSubmit={submit}>
        <label htmlFor="pf-view-input">{CONNECT.viewLabel}</label>
        <span className="pf-view-row">
          <input id="pf-view-input" className="smap-addr pf-view-input" value={draft} placeholder="0x…" spellCheck={false} autoComplete="off"
            aria-invalid={bad || undefined} onChange={e => { setDraft(e.target.value); setBad(false); }} />
          <button type="submit" className="te-link pf-view-go">{CONNECT.view}</button>
        </span>
        {bad && <span className="pf-view-error">{CONNECT.invalid}</span>}
      </form>
    </div></div>
  </div>;
}

function LoadingShapes({ phone }) {
  return <div aria-hidden="true">
    <div className={phone ? "pf-strip-ph" : "pf-strip"}>{(phone ? [0] : [0, 1, 2, 3]).map(i => <div key={i} className="pf-cell"><Skeleton width={70} height={10} /><Skeleton width="55%" height={28} /><Skeleton width="100%" height={8} /></div>)}</div>
    <div className="pf-skel-rows">{[0, 1, 2, 3, 4].map(i => <div key={i} className="pf-skel-row"><Skeleton width={150} height={14} /><span className="pf-skel-track" /><Skeleton width={90} height={12} /></div>)}</div>
  </div>;
}

export default function PortfolioPage({ api, preview = false }) {
  const { effectiveAddress: account, readOnly, setViewAddress, walletClient, connect, error: walletError } = useWallet();
  const { isMobile: phone, width } = useViewport();
  const navigate = useNavigate();
  const [sp, setSp] = useSearchParams();
  const setParam = useCallback((k, v) => setSp(prev => {
    const n = new URLSearchParams(prev);
    if (v == null || v === "") n.delete(k); else n.set(k, v);
    return n;
  }, { replace: true }), [setSp]);
  const fit = sp.get("fit") === "1d" ? "1d" : "4h";
  const sort = ["size", "pnl"].includes(sp.get("sort")) ? sp.get("sort") : "closest";
  const selected = useMemo(() => new Set((sp.get("check") || "").split(",").map(k => KEY_OF_URL[k]).filter(Boolean)), [sp]);
  const openCoin = sp.get("open");
  const period = sp.get("period") || "1m";
  const mode = sp.get("mode") === "equity" ? "equity" : "pnl";
  const tab = sp.get("tab") || "orders";
  const showHeld = width >= 1180;

  const f = usePortfolioFeeds(account);
  const names = useMemo(() => spotNames(f.spotMeta), [f.spotMeta]);
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => { const t = setInterval(() => setNowMs(Date.now()), 30_000); return () => clearInterval(t); }, []);

  // Positions on every venue, largest first; the context covers the 12 largest.
  const positions = useMemo(() => {
    const out = [...positionsOf(f.main, "main"), ...positionsOf(f.xyz, "xyz")];
    for (const [dex, st] of Object.entries(f.others || {})) out.push(...positionsOf(st, dex));
    return out.sort((a, b) => b.value - a.value);
  }, [f.main, f.xyz, f.others]);
  const coinsKey = useMemo(() => positions.slice(0, 12).map(p => p.coin).sort().join(","), [positions]);
  const reflex = useReflex(coinsKey);
  // The scanner's context answered: until it does (or after it fails), what it reads is unknown.
  const ctxKnown = !!reflex.ctx && !reflex.ctxFailed;
  // Funding rates for the venues held, read once per visit (the rows' carry).
  const assetCtx = useHeldAssetCtx(positions.map(p => p.coin));

  const rows = useMemo(() => positions.map(p => buildRow(p, reflex.ctx?.coins?.[p.coin],
    p.venue === "main" ? f.orders : p.venue === "xyz" ? f.ordersXyz : [],
    { ordersRead: p.venue === "main" ? f.ordersRead.main : p.venue === "xyz" ? f.ordersRead.xyz : false })),
  [positions, reflex.ctx, f.orders, f.ordersXyz, f.ordersRead.main, f.ordersRead.xyz]);

  const failedVenues = f.failed.filter(k => VENUE_FEEDS.has(k)).map(k => FEEDS[k]);
  const totals = useMemo(() => computeTotals({
    main: f.main, dexs: { ...(f.xyz ? { xyz: f.xyz } : {}), ...(f.others || {}) }, spot: f.spot, spotMeta: f.spotMeta, mids: f.mids,
    earn: f.earn, delegator: f.delegator, vaults: f.vaults, unified: !!f.abstraction && f.abstraction !== "disabled", failed: [...new Set(failedVenues)],
  }), [f.main, f.xyz, f.others, f.spot, f.spotMeta, f.mids, f.earn, f.delegator, f.vaults, f.abstraction, failedVenues.join()]); // eslint-disable-line react-hooks/exhaustive-deps

  const classified = useMemo(() => classifyFills(f.fills, { includeDex: true }), [f.fills]);
  const trips = useMemo(() => roundTrips(classified), [classified]);
  const fillsStart = f.fills?.length ? f.fills[0].time : null;
  const openAtOf = coin => trips.open[coin]?.openedAt ?? null;
  const evOf = coin => (reflex.ev?.coins?.[coin] ? { ...reflex.ev.coins[coin], windowStart: reflex.ev.window_start } : null);

  // Since: two slots in this browser; the baseline is fixed for the visit.
  const slots = useMemo(() => {
    let storage = null;
    try { storage = window.localStorage; } catch { /* blocked */ }
    return account ? readSlots(storage, account, Date.now()) : { base: null };
  }, [account]);
  const [sinceMode, setSinceMode] = useState(null);
  const mode2 = sinceMode || (slots.base ? "visit" : "24h");
  const snap = useMemo(() => (f.main ? buildSnapshot({ t: nowMs, equity: totals.equity, upnl: totals.openPnl,
    lastFillT: f.fills?.length ? f.fills[f.fills.length - 1].time : null, rows }) : null), [f.main, rows, totals.equity, totals.openPnl, f.fills, nowMs]);
  const snapRef = useRef(null);
  snapRef.current = snap;
  useEffect(() => {
    if (!account) return undefined;
    const write = () => { if (!snapRef.current) return; try { writeCurrent(window.localStorage, account, slots.base, snapRef.current); } catch { /* blocked */ } };
    const stop = pollWhileVisible(write, 60_000);
    const onHide = () => { if (document.hidden) write(); };
    document.addEventListener("visibilitychange", onHide);
    window.addEventListener("pagehide", write);
    return () => { stop(); document.removeEventListener("visibilitychange", onHide); window.removeEventListener("pagehide", write); };
  }, [account, slots]);
  const sinceBase = mode2 === "visit" ? slots.base : (f.main ? base24h(rows, reflex.ev, trips, f.fills, nowMs) : null);
  const changes = useMemo(() => (snap && sinceBase ? sinceChanges(sinceBase, snap, { trips: trips.closed }) : []), [snap, sinceBase, trips]);
  const summary = useMemo(() => {
    if (!sinceBase) return null;
    if (mode2 === "24h") {
      const day = f.portfolio?.day?.pnlHistory;
      return { t: sinceBase.t, pnl: day?.length ? day[day.length - 1].value : 0, fills: (f.fills || []).filter(x => x.time > sinceBase.t).length };
    }
    return sinceSummary(sinceBase, { fills: f.fills || [], funding: f.funding || [], upnl: totals.openPnl });
  }, [sinceBase, mode2, f.portfolio, f.fills, f.funding, totals.openPnl]);

  // Checks, filter, sort, groups. A check that reads missing context cannot filter.
  const counts = useMemo(() => countChecks(rows), [rows]);
  const active = useMemo(() => (ctxKnown ? selected : new Set([...selected].filter(k => !CTX_CHECKS.has(k)))), [selected, ctxKnown]);
  const visible = useMemo(() => sortRows(filterRows(rows, active), sort), [rows, active, sort]);
  const quiet = quietNoStop(counts, rows.length);
  const sides = useMemo(() => new Map(rows.map(r => [r.coin, r.isLong])), [rows]);
  const groups = useMemo(() => ({
    main: visible.filter(r => r.venue === "main"), xyz: visible.filter(r => r.venue === "xyz"),
    other: visible.filter(r => r.venue !== "main" && r.venue !== "xyz"),
  }), [visible]);
  const toggleCheck = k => {
    const n = new Set(selected);
    n.has(k) ? n.delete(k) : n.add(k);
    setParam("check", CHECK_KEYS.filter(x => n.has(x)).map(x => URL_KEYS[x]).join(","));
  };

  // Scroll to a row, one 1.2 s highlight.
  const [flash, setFlash] = useState(null);
  const pick = useCallback(coin => {
    const el = document.querySelector(`[data-coin="${CSS.escape(coin)}"]`);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
    setFlash(coin);
    setTimeout(() => setFlash(c => (c === coin ? null : c)), 1200);
  }, []);

  // Watch (the same store and toast as the Radar).
  const { data: map4h, watched, telegram, toggleWatch } = useSetupMap("4h");
  const [toast, setToast] = useState("");
  useEffect(() => { if (!toast) return undefined; const t = setTimeout(() => setToast(""), 3500); return () => clearTimeout(t); }, [toast]);
  const onWatch = useCallback(async coin => setToast(watchToast(coin, await toggleWatch(coin, "4h"), telegram)), [toggleWatch, telegram]);

  // Close and cancel: tradeActions.js. The sheet replaces window.confirm only with PF_CONFIRM_SHEET
  // on; on the preview route it shows for review and sends nothing.
  const [closing, setClosing] = useState(null);
  const [cancelling, setCancelling] = useState(null);
  const [notice, setNotice] = useState(null);
  const [sheet, setSheet] = useState(null);           // {row, anchor, resolve}
  const anchorRef = useRef(null);
  const rowsRef = useRef(rows);
  rowsRef.current = rows;
  const actions = useMemo(() => makeTradeActions({
    api, hlClient, readOnly, walletClient, setClosing, setCancelling, setActionNotice: setNotice, fetchFast: f.fetchFast,
    confirm: PF_CONFIRM_SHEET
      ? coin => new Promise(resolve => setSheet({ row: rowsRef.current.find(r => r.coin === coin), anchor: anchorRef.current, resolve }))
      : undefined,
  }), [api, readOnly, walletClient, f.fetchFast]); // eslint-disable-line react-hooks/exhaustive-deps
  const canClose = !readOnly && !!walletClient;
  const onClose = (row, anchor) => {
    if (preview) { setSheet({ row, anchor, resolve: null }); return; }
    anchorRef.current = anchor;
    const { coin, size, isLong } = closeArgs({ coin: row.coin, szi: row.szi });
    actions.closePosition(coin, size, isLong);
  };
  const onCancel = (coin, oid) => {
    if (preview) { setNotice({ section: "orders", coin, tone: "ok", text: ROWS.preview }); return; }
    actions.cancelOrd(coin, oid);
  };
  const endSheet = ok => { sheet?.resolve?.(ok); setSheet(null); };

  const toggleOpen = coin => setParam("open", openCoin === coin ? null : coin);
  useEffect(() => {
    if (!openCoin) return undefined;
    const onKey = e => { if (e.key === "Escape" && !document.querySelector(".pf-sheet-pop")) setParam("open", null); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [openCoin, setParam]);

  const [copied, setCopied] = useState(false);
  useEffect(() => { if (!copied) return undefined; const t = setTimeout(() => setCopied(false), 1600); return () => clearTimeout(t); }, [copied]);

  if (!account) return <div className="pf-page pf-v2"><NoWallet connect={connect} walletError={walletError} setViewAddress={setViewAddress} /></div>;

  const lastMainAt = f.lastMainAt;
  const ageMs = lastMainAt ? nowMs - lastMainAt : 0;
  const staleHard = lastMainAt && ageMs > STALE_HARD_MS;
  const loading = !f.main && !f.feeds.main?.error;
  const failedNames = [...new Set([...f.failedNames, ...(reflex.failed ? [FEEDS.context] : [])])];
  const retry = () => { f.retry(); reflex.retry(); };
  const lastClosed = trips.closed[0];
  const mapData = map4h;

  const renderRow = row => {
    const open = openCoin === row.coin;
    const venueFailed = (row.venue === "xyz" && f.feeds.xyz?.error) || (row.venue === "main" && f.feeds.main?.error);
    return <div key={row.coin} className="pf-row-wrap">
      <BoardRow row={row} names={names} ev={evOf(row.coin)} openAt={openAtOf(row.coin)} watching={watched.has(kKey(row.coin))}
        onWatch={onWatch} onClose={onClose} closing={closing === row.coin} canClose={canClose} open={open} onToggle={() => toggleOpen(row.coin)}
        flash={flash === row.coin} showHeld={showHeld} now={nowMs} dim={venueFailed}
        quietNoStop={quiet} visit={slots.base?.coins?.[row.coin]} visitT={slots.base?.t} rate={assetCtx.get(row.coin)?.funding} />
      {notice?.coin === row.coin && <ActionNotice notice={notice} onDismiss={() => setNotice(null)} />}
      {open && <PositionDetail row={row} classified={classified} trip={trips.open[row.coin]} ev={evOf(row.coin)} openAt={openAtOf(row.coin)}
        windowStart={fillsStart ? fillsStart / 1000 : null} canCancel={canClose} onCancel={onCancel} cancelling={cancelling} />}
    </div>;
  };
  const renderCard = row => <PhoneCard key={row.coin} row={row} names={names} now={nowMs} flash={flash === row.coin} onOpen={() => toggleOpen(row.coin)}
    quietNoStop={quiet} visit={slots.base?.coins?.[row.coin]} />;
  const sheetRow = phone && openCoin ? rows.find(r => r.coin === openCoin) : null;
  const marks = new Map(rows.map(r => [r.coin, r.mark]));

  return <div className={`pf-page pf-v2${staleHard ? " pf-is-stale" : ""}`}>
    <TitleRow address={account} readOnly={readOnly} onStopViewing={() => setViewAddress("")} lastMainAt={lastMainAt}
      failedNames={failedNames} onRetry={retry} onCopied={() => setCopied(true)} phone={phone} />
    {loading ? <LoadingShapes phone={phone} /> : <>
      <RiskStrip totals={totals} rows={rows} day={f.portfolio?.day} partialNames={totals.failed} tf={fit} onTf={k => setParam("fit", k === "1d" ? "1d" : null)}
        map={mapData} onPick={pick} onRadar={() => navigate("/radar?tf=4h")} phone={phone} stale={staleHard} ctxKnown={ctxKnown} />
      {(sinceBase || slots.base) && <SinceRow mode={mode2} onMode={setSinceMode} summary={summary} changes={changes} onPick={pick} phone={phone} hasBase={!!slots.base} />}
      {rows.length > 0 && <ChecksRow counts={counts} selected={active} onToggle={toggleCheck} sort={sort} onSort={k => setParam("sort", k === "closest" ? null : k)} phone={phone} ctxKnown={ctxKnown} />}
      {rows.length > 0 && phone && <SortRow sort={sort} onSort={k => setParam("sort", k === "closest" ? null : k)} />}
      {rows.length > 0 ? <div className={staleHard ? "pf-stale" : ""}>
        <Board groups={groups} phone={phone} showHeld={showHeld} ctxAsOf={reflex.ctx?.stale ? reflex.ctx : null} renderRow={renderRow} renderCard={renderCard} />
      </div> : <div className="pf-noneline"><span className="pf-t2">{ROWS.noPositions}</span>
        {lastClosed && <span className="pf-t3"> {ROWS.lastClosed([displayName(lastClosed.coin).name, displayName(lastClosed.coin).suffix].filter(Boolean).join(" "), lastClosed.side, usd(lastClosed.pnl, { sign: true }), fmtAge(nowMs / 1000 - lastClosed.closedAt))}</span>}</div>}
      {notice && !rows.some(r => r.coin === notice.coin) && <ActionNotice notice={notice} onDismiss={() => setNotice(null)} />}
      <Performance portfolio={f.portfolio} period={period} onPeriod={k => setParam("period", k === "1m" ? null : k)} mode={mode} onMode={k => setParam("mode", k === "pnl" ? null : k)}
        fills={f.fills} funding={f.funding} fillsStart={fillsStart} lastVisit={slots.base ? slots.base.t / 1000 : null} phone={phone} />
      <ActivityTabs tab={tab} onTab={k => setParam("tab", k === "orders" ? null : k)} orders={[...(f.orders || []), ...(f.ordersXyz || [])]} marks={marks} sides={sides}
        fills={f.fills} funding={f.funding} names={names} canCancel={canClose} onCancel={onCancel} cancelling={cancelling} phone={phone} />
    </>}
    {sheetRow && <RadarSheet open onClose={() => setParam("open", null)} labelledBy="pf-sheet-h">
      <div className="pf-sh-head" id="pf-sheet-h"><CoinName coin={sheetRow.coin} names={names} size={20} />
        <span className="pf-side">{sheetRow.isLong ? ROWS.long : ROWS.short}{sheetRow.lev != null && <span className="pf-t3 m"> {sheetRow.lev}x</span>}</span>
        <span className={`m pf-sh-pnl ${pnlClass(sheetRow.upnl)}`}>{usd(sheetRow.upnl, { sign: true })}</span></div>
      <PositionDetail row={sheetRow} classified={classified} trip={trips.open[sheetRow.coin]} ev={evOf(sheetRow.coin)} openAt={openAtOf(sheetRow.coin)}
        windowStart={fillsStart ? fillsStart / 1000 : null} canCancel={canClose} onCancel={onCancel} cancelling={cancelling} phone />
      {sheet?.row?.coin === sheetRow.coin ? <CloseBody row={sheetRow} preview={preview} onConfirm={() => endSheet(true)} onKeep={() => endSheet(false)} />
        : <div className="pf-sh-acts"><Actions row={sheetRow} watching={watched.has(kKey(sheetRow.coin))} onWatch={onWatch} onClose={onClose} closing={closing === sheetRow.coin} canClose={canClose} /></div>}
    </RadarSheet>}
    {sheet && !phone && <CloseConfirm row={sheet.row} anchor={sheet.anchor} preview={preview} onConfirm={() => endSheet(true)} onKeep={() => endSheet(false)} />}
    {copied && <div className="smap-toast" role="status">{IDENTITY.copied}</div>}
    {toast && <div className="smap-toast" role="status">{toast}</div>}
  </div>;
}
