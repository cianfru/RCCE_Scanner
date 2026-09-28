import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation, useNavigate } from "react-router-dom";
import { T, getBaseSymbol } from "../theme.js";
import useViewport from "../hooks/useViewport.js";
import useSetupMap from "../hooks/useSetupMap.js";
import useMyPositions from "../hooks/useMyPositions.js";
import useSetupIntel from "../hooks/useSetupIntel.js";
import useFavorites from "../hooks/useFavorites.js";
import { useWallet } from "../WalletContext.jsx";
import { timeframeFrom } from "../utils/researchNavigation.js";
import { altBaseline, groupStats, inGroup, SECTOR_SHORT } from "../utils/sectors.js";
import { fmtIn, nextCloses } from "../utils/intel.js";
import { isAddress, newEarly, picks, visible, watchToast } from "../utils/setupMap.js";
import { moneyMode, sameSpot } from "../utils/radarDepth.js";
import { clampLeft, placeVertical } from "../utils/tooltipPosition.js";
import PageTitle from "../components/PageTitle.jsx";
import Tabs from "../components/Tabs.jsx";
import SetupIntelDrawer from "../components/SetupIntelDrawer.jsx";
import RadarPicks from "../components/radar/RadarPicks.jsx";
import RadarMap from "../components/radar/RadarMap.jsx";
import RadarRail, { FocusBody } from "../components/radar/RadarRail.jsx";
import RadarLadder from "../components/radar/RadarLadder.jsx";
import RadarSheet from "../components/radar/RadarSheet.jsx";
import { RM, store } from "../components/radar/shared.jsx";

const TF_ITEMS = [{ key: "4h", label: "4H" }, { key: "1d", label: "1D" }];
const VIEW_ITEMS = [{ key: "setups", label: "Setups with traders" }, { key: "all", label: "All coins" }];
const MINUS = "−";
const pct = x => (x === 0 ? "0%" : `${x > 0 ? "+" : MINUS}${Math.abs(x)}%`);

// A sector (or ecosystem, or "Sector|Ecosystem" pocket) as the scanner chips name it.
export const groupLabel = name => (name ? name.split("|").map(n => SECTOR_SHORT[n] || n).join(" · ") : "");
function groupBy(rows, name, hint) {
  if (!name) return "sector";
  if (name.includes("|")) return "pocket";
  if (hint === "ecosystem" || hint === "sector") return hint;
  return rows.some(r => r.sector === name) || !rows.some(r => r.ecosystem === name) ? "sector" : "ecosystem";
}

// A small list under a button (the sector and the view pickers): placed inside the viewport,
// closed by Escape or a tap outside.
function usePopover(open, setOpen, anchor, pop, width = 280) {
  const [pos, setPos] = useState(null);
  useLayoutEffect(() => {
    if (!open) { setPos(null); return undefined; }
    const place = () => {
      const r = anchor.current.getBoundingClientRect();
      const w = Math.min(width, window.innerWidth - 24);
      const h = pop.current?.getBoundingClientRect().height || 320;
      setPos({ left: clampLeft(r.left, r.width, w, window.innerWidth), ...placeVertical(r.top, r.bottom, h, window.innerHeight, 8), width: w });
    };
    const dismiss = e => {
      if (e.key === "Escape" || (e.type === "pointerdown" && !anchor.current?.contains(e.target) && !pop.current?.contains(e.target))) setOpen(false);
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    document.addEventListener("keydown", dismiss);
    document.addEventListener("pointerdown", dismiss);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
      document.removeEventListener("keydown", dismiss);
      document.removeEventListener("pointerdown", dismiss);
    };
  }, [open, setOpen, anchor, pop, width]);
  return pos;
}

// "All sectors": a list of the sectors with their member count and lead, in the chip colours.
function SectorPicker({ rows, value, onChange }) {
  const [open, setOpen] = useState(false);
  const anchor = useRef(null), pop = useRef(null);
  const id = useId();
  const pos = usePopover(open, setOpen, anchor, pop);
  const groups = useMemo(() => (open ? groupStats(rows, "sector", null, altBaseline(rows)).filter(g => !g.tail || g.rows >= 2) : []), [open, rows]);
  const pick = v => { setOpen(false); onChange(v); };
  return <>
    <button ref={anchor} type="button" className="radar-sector-btn" aria-haspopup="listbox" aria-expanded={open} aria-controls={open ? id : undefined}
      onClick={() => setOpen(o => !o)}>{value ? groupLabel(value) : "All sectors"}</button>
    {open && createPortal(<div ref={pop} id={id} className="radar-sector-pop reflex-terminal" role="listbox" aria-label="Sector"
      style={{ ...pos, visibility: pos ? "visible" : "hidden" }}>
      <button type="button" role="option" aria-selected={!value} className="radar-sector-opt" onClick={() => pick(null)}><span>All sectors</span></button>
      {groups.map(g => <button key={g.name} type="button" role="option" aria-selected={value === g.name} className="radar-sector-opt" data-dir={g.dir}
        onClick={() => pick(g.name)}>
        <span>{SECTOR_SHORT[g.name] || g.name}<small>{g.tail ? g.rows : g.n}</small></span>
        {!g.tail && <b>{g.shown == null ? "—" : pct(g.shown)}</b>}
      </button>)}
    </div>, document.body)}
  </>;
}

// Which coins the map shows: the setups with traders (default) or all coins, and your trades
// on or off. One button with the current view; the choices one click deeper.
function ViewPicker({ showAll, onView, mineOn, onMine }) {
  const [open, setOpen] = useState(false);
  const anchor = useRef(null), pop = useRef(null);
  const id = useId();
  const pos = usePopover(open, setOpen, anchor, pop, 240);
  return <>
    <button ref={anchor} type="button" className="radar-sector-btn" aria-haspopup="true" aria-expanded={open} aria-controls={open ? id : undefined}
      onClick={() => setOpen(o => !o)}>{showAll ? "All coins" : "Setups with traders"}{mineOn ? " · My trades" : ""}</button>
    {open && createPortal(<div ref={pop} id={id} className="radar-sector-pop reflex-terminal" role="group" aria-label="Coins on the map"
      style={{ ...pos, visibility: pos ? "visible" : "hidden" }}>
      {VIEW_ITEMS.map(v => <button key={v.key} type="button" aria-pressed={(v.key === "all") === showAll} className="radar-sector-opt"
        onClick={() => { setOpen(false); onView(v.key); }}><span>{v.label}</span></button>)}
      <span className="radar-pop-rule" aria-hidden="true" />
      <button type="button" aria-pressed={mineOn} className="radar-sector-opt radar-mine-opt" onClick={onMine}>
        <span><svg className="grid-aligned-box" width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
          <rect x="1" y="1" width="10" height="10" rx="2" />
          {mineOn && <path d="M3.4 6.2l1.8 1.8 3.5-3.8" />}
        </svg>My trades</span>
      </button>
    </div>, document.body)}
  </>;
}

// "Next 1D close in 8h 13m", kept current.
function NextClose({ tf }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 30000); return () => clearInterval(t); }, []);
  return <span className="radar-meta">Next {tf.toUpperCase()} close in <b>{fmtIn(nextCloses(tf, now, 1)[0] - now)}</b></span>;
}

// The Radar page (/radar): the day's picks, the full setup map with its rail, and the phone
// sheet. The address holds the timeframe, the followed coin, the sector and the view.
export default function RadarPage({ results4h, results1d, onSelect }) {
  const { width } = useViewport();
  const phone = width < 768;
  const location = useLocation();
  const navigate = useNavigate();
  const params = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const tf = timeframeFrom(location.search);
  const focus = params.get("focus") || null;
  const sector = params.get("sector") || null;
  const showAll = params.get("view") === "all";
  const spotArrival = params.get("market") === "spot";

  // Change the address: the followed coin and the timeframe replace the entry, the rest adds one.
  const setParams = useCallback((changes, replace) => {
    const p = new URLSearchParams(location.search);
    for (const [k, v] of Object.entries(changes)) (v == null || v === "") ? p.delete(k) : p.set(k, v);
    p.delete("market");
    const { restoreScroll, ...state } = location.state || {};
    navigate(`/radar?${p}`, { replace, state });
  }, [navigate, location.search, location.state]);
  const setFocus = useCallback(coin => setParams({ focus: coin }, true), [setParams]);

  const rows = tf === "4h" ? results4h : results1d;
  const perps = useMemo(() => (rows || []).filter(r => (r.market_kind || "perpetual") === "perpetual"), [rows]);
  const by = groupBy(perps, sector, params.get("by"));
  const results = useMemo(() => (sector ? perps.filter(r => inGroup(r, by, sector)) : perps), [perps, sector, by]);

  const [mineOn, setMineOn] = useState(() => store.get("smap-mine") === "1");
  const [addressDraft, setAddressDraft] = useState("");
  const [detail, setDetail] = useState(null);
  const [msg, setMsg] = useState("");
  const { data, watched, telegram, toggleWatch } = useSetupMap(tf);
  const { effectiveAddress, setViewAddress } = useWallet();
  // My trades: the shared address, else the executor's positions; nothing while the toggle is off.
  const { byCoin: mineBy, loading: mineLoading } = useMyPositions(mineOn ? (effectiveAddress || null) : null, { executorFallback: mineOn && !effectiveAddress });
  const { isFav, toggle: toggleFav } = useFavorites();
  const allowed = useMemo(() => new Set(results.map(r => r.symbol)), [results]);
  const coins = useMemo(() => (data?.coins || []).filter(c => allowed.has(c.symbol)), [data, allowed]);
  const box = data?.box || { z: [-0.5, 1.5], n: [1, 8] };
  const keep = useMemo(() => new Set([...watched, ...mineBy.keys(), ...(focus ? [focus] : [])]), [watched, mineBy, focus]);
  const pts = useMemo(() => visible(coins, { all: showAll, keep }), [coins, showAll, keep]);
  const top = useMemo(() => picks(coins, box), [coins, box]);
  const inBoxN = useMemo(() => coins.filter(c => c.zone === "watch").length, [coins]);
  const fresh = useMemo(() => newEarly(coins, box, 6), [coins, box]);
  const moneyOn = useMemo(() => moneyMode(coins), [coins]);
  const byCoin = useMemo(() => new Map(coins.map(c => [c.coin, c])), [coins]);
  const focusC = focus ? byCoin.get(focus) || null : null;
  const rowFor = useCallback(coin => results.find(r => getBaseSymbol(r.symbol) === coin) || null, [results]);
  const detailRow = detail ? rowFor(detail) : null;
  // One request for the followed coin (the drawer opens on it). The focus panel, the sheet and
  // the drawer show the same mark price and time.
  const intelCoin = detail || (focusC ? focus : null);
  const intel = useSetupIntel(intelCoin ? [intelCoin] : []);

  useEffect(() => { if (!msg) return undefined; const t = setTimeout(() => setMsg(""), 3500); return () => clearTimeout(t); }, [msg]);
  const onWatch = useCallback(async coin => setMsg(watchToast(coin, await toggleWatch(coin), telegram)), [toggleWatch, telegram]);
  const pick = useCallback(coin => setFocus(focus === coin ? null : coin), [setFocus, focus]);
  const clear = useCallback(() => setFocus(null), [setFocus]);
  const openChart = useCallback(row => onSelect(row), [onSelect]);

  // Map height on desktop: what is left of the first screen under the header, title and picks,
  // after the card's player band (52: Replay and the map key), its border and a 16px margin, so
  // the whole card is in view on arrival. Fixed below 1200px.
  const [vh, setVh] = useState(() => (typeof window !== "undefined" ? window.innerHeight : 900));
  useEffect(() => { const on = () => setVh(window.innerHeight); window.addEventListener("resize", on); return () => window.removeEventListener("resize", on); }, []);
  const mainRef = useRef(null);
  const [mainTop, setMainTop] = useState(318);
  useLayoutEffect(() => {
    const el = mainRef.current;
    if (!el) return;
    const t = Math.round(el.getBoundingClientRect().top + window.scrollY);
    if (t > 0 && Math.abs(t - mainTop) > 1) setMainTop(t);
  });
  const mapH = width >= 1200 ? Math.max(480, Math.min(760, vh - mainTop - 52 - 2 - 16)) : width >= 768 ? 480 : 400;
  // Where each coin sits on the map at rest, for the ladder's "Same spot" (coins stacked there).
  const [restPos, setRestPos] = useState(null);
  const onRest = useCallback(pos => setRestPos(prev => {
    if (prev && prev.size === pos.size && [...pos].every(([k, p]) => { const q = prev.get(k); return q && Math.abs(q.x - p.x) < 0.5 && Math.abs(q.y - p.y) < 0.5; })) return prev;
    return new Map(pos);
  }), []);
  const stack = useMemo(() => (focusC && restPos ? sameSpot(restPos, focusC.coin) : []), [focusC, restPos]);

  const stripWatch = [...watched].map(c => byCoin.get(c)).filter(Boolean);
  const stripMine = [...mineBy.values()].map(m => [byCoin.get(m.coin), m]).filter(x => x[0]);
  const loaded = !!data && perps.length > 0;
  const focusIntel = focusC ? intel?.coins?.[focusC.coin] || null : null;
  const focusProps = focusC && {
    c: focusC, tf, box, row: rowFor(focusC.coin), intel: focusIntel, updatedAt: intel?.updated_at, watched, mine: mineBy.get(focusC.coin), starred: !!rowFor(focusC.coin) && isFav(rowFor(focusC.coin).symbol),
    onStar: toggleFav, onWatch, onClear: clear, onDetail: () => setDetail(focusC.coin), onChart: openChart,
  };
  // The followed coin: its price ladder (as tall as the map card on wide screens, leaving the
  // top of the readings in view under it), then its readings and actions.
  const cardH = mapH + 52 + 2;
  const focusSlot = !phone && focusC
    ? <>
      <RadarLadder c={focusC} tf={tf} mark={focusIntel?.mark} cardHeight={width >= 1200 ? Math.max(420, cardH - 88) : null} plotHeight={440} stack={stack} onPick={setFocus} />
      <section className="smap-focus radar-focus" aria-labelledby="radar-focus-h"><FocusBody {...focusProps} withLadder titleId="radar-focus-h" /></section>
    </>
    : !focusC ? <p className="radar-hint">Tap a bubble to see who holds it.</p> : null;
  // The sheet keeps showing its coin while it slides away.
  const sheetProps = useRef(null);
  if (focusProps) sheetProps.current = focusProps;
  // Phone: the tapped dot (and its trail) stays in view in the band above the sheet.
  useEffect(() => {
    if (!phone || !focusC) return undefined;
    let id = requestAnimationFrame(() => { id = requestAnimationFrame(() => {
      const dot = document.querySelector(".radar-mapcard .smap-dot.on .smap-core");
      const sheet = document.querySelector(".radar-sheet");
      if (!dot || !sheet) return;
      const top = Math.max(0, document.querySelector(".terminal-header")?.getBoundingClientRect().bottom || 0);
      const sheetTop = window.innerHeight - (parseFloat(getComputedStyle(sheet).bottom) || 0) - sheet.offsetHeight;
      const r = dot.getBoundingClientRect(), mid = r.top + r.height / 2;
      if (mid < top + 48 || mid > sheetTop - 48) window.scrollBy({ top: mid - (top + sheetTop) / 2, behavior: RM ? "auto" : "smooth" });
    }); });
    return () => cancelAnimationFrame(id);
  }, [phone, focus, !!focusC]);
  const toggleMine = () => { const v = !mineOn; setMineOn(v); store.set("smap-mine", v ? "1" : "0"); };

  return (
    <div className="radar-page">
      <div className="scanner-head radar-head" style={{ padding: `${phone ? T.sp4 : T.sp3}px 0 ${T.sp1}px` }}>
        <div className="radar-head-left">
          <PageTitle>Radar</PageTitle>
          <Tabs small label="Timeframe" items={TF_ITEMS} value={tf} onChange={k => setParams({ tf: k }, true)} />
          <NextClose tf={tf} />
          {sector && <span className="radar-meta radar-sector-line">{groupLabel(sector)} · <button type="button" className="te-link" onClick={() => setParams({ sector: null, by: null })}>Show all</button></span>}
        </div>
        <div className="radar-head-right">
          <SectorPicker rows={perps} value={sector} onChange={v => setParams({ sector: v, by: null })} />
          <ViewPicker showAll={showAll} onView={k => setParams({ view: k === "all" ? "all" : null })} mineOn={mineOn} onMine={toggleMine} />
        </div>
      </div>
      {mineOn && !effectiveAddress && <div className="radar-addr-row">
        <input className="smap-addr" value={addressDraft} placeholder="Hyperliquid address (blank: executor)" aria-label="Hyperliquid address for My trades" spellCheck={false}
          onChange={e => { const v = e.target.value.trim(); setAddressDraft(v); if (isAddress(v)) setViewAddress(v); }} />
      </div>}
      {spotArrival && <p className="radar-spot-note">The Radar covers Hyperliquid perpetuals.</p>}

      <RadarPicks top={top} box={box} tf={tf} focus={focusC ? focus : null} watched={watched} inBox={inBoxN} loaded={loaded} onPick={pick} />

      <div className="radar-main" ref={mainRef}>
        <RadarMap pts={pts} byCoin={byCoin} box={box} data={loaded ? data : null} tf={tf} height={mapH} focus={focusC ? focus : null} watched={watched}
          mineBy={mineBy} mineOn={mineOn} keep={keep} onPick={pick} onRest={onRest} moneyOn={moneyOn} />
        <RadarRail focusSlot={focusSlot} stripWatch={stripWatch} stripMine={stripMine} mineOn={mineOn} mineLoading={mineLoading}
          fresh={fresh} onPick={pick} />
      </div>

      {phone && <RadarSheet open={!!focusC} onClose={clear} labelledBy="radar-sheet-h">
        {sheetProps.current && <FocusBody {...sheetProps.current} withLadder titleId="radar-sheet-h">
          {focusC && <RadarLadder c={focusC} tf={tf} mark={focusIntel?.mark} compact plotHeight={380} stack={stack} onPick={setFocus} />}
        </FocusBody>}
      </RadarSheet>}

      {msg && <div className="smap-toast" role="status">{msg}</div>}
      {detail && detailRow && <SetupIntelDrawer row={detailRow} coin={byCoin.get(detail)} intel={intel?.coins?.[detail] || null} updatedAt={intel?.updated_at}
        watching={watched.has(detail)} onWatch={() => onWatch(detail)}
        onOpenChart={row => { setDetail(null); onSelect(row); }} onClose={() => setDetail(null)} />}
    </div>
  );
}
