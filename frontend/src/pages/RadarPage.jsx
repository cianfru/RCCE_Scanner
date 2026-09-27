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
import { isAddress, movers, picks, visible, watchToast } from "../utils/setupMap.js";
import { clampLeft, placeVertical } from "../utils/tooltipPosition.js";
import PageTitle from "../components/PageTitle.jsx";
import Tabs from "../components/Tabs.jsx";
import SetupIntelDrawer from "../components/SetupIntelDrawer.jsx";
import RadarPicks from "../components/radar/RadarPicks.jsx";
import RadarMap from "../components/radar/RadarMap.jsx";
import RadarRail, { FocusBody } from "../components/radar/RadarRail.jsx";
import RadarSheet from "../components/radar/RadarSheet.jsx";
import { store } from "../components/radar/shared.jsx";

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

// "All sectors": a list of the sectors with their member count and lead, in the chip colours.
function SectorPicker({ rows, value, onChange }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState(null);
  const anchor = useRef(null), pop = useRef(null);
  const id = useId();
  const groups = useMemo(() => (open ? groupStats(rows, "sector", null, altBaseline(rows)).filter(g => !g.tail || g.rows >= 2) : []), [open, rows]);
  useLayoutEffect(() => {
    if (!open) { setPos(null); return undefined; }
    const place = () => {
      const r = anchor.current.getBoundingClientRect();
      const w = Math.min(280, window.innerWidth - 24);
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
  }, [open]);
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
  const mv = useMemo(() => movers(coins, box), [coins, box]);
  const byCoin = useMemo(() => new Map(coins.map(c => [c.coin, c])), [coins]);
  const focusC = focus ? byCoin.get(focus) || null : null;
  const rowFor = useCallback(coin => results.find(r => getBaseSymbol(r.symbol) === coin) || null, [results]);
  const detailRow = detail ? rowFor(detail) : null;
  // One request for the drawer's coin and the market-wide pulse in the rail.
  const intel = useSetupIntel(detail ? [detail] : [], { pulse: true });

  useEffect(() => { if (!msg) return undefined; const t = setTimeout(() => setMsg(""), 3500); return () => clearTimeout(t); }, [msg]);
  const onWatch = useCallback(async coin => setMsg(watchToast(coin, await toggleWatch(coin), telegram)), [toggleWatch, telegram]);
  const pick = useCallback(coin => setFocus(focus === coin ? null : coin), [setFocus, focus]);
  const clear = useCallback(() => setFocus(null), [setFocus]);
  const openChart = useCallback(row => onSelect(row), [onSelect]);

  // Map height: the viewport minus the header, title and picks on desktop; fixed below.
  const [vh, setVh] = useState(() => (typeof window !== "undefined" ? window.innerHeight : 900));
  useEffect(() => { const on = () => setVh(window.innerHeight); window.addEventListener("resize", on); return () => window.removeEventListener("resize", on); }, []);
  const mapH = width >= 1200 ? Math.max(520, Math.min(760, vh - 380)) : width >= 768 ? 480 : 400;

  const stripWatch = [...watched].map(c => byCoin.get(c)).filter(Boolean);
  const stripMine = [...mineBy.values()].map(m => [byCoin.get(m.coin), m]).filter(x => x[0]);
  const loaded = !!data && perps.length > 0;
  const focusProps = focusC && {
    c: focusC, tf, box, row: rowFor(focusC.coin), watched, mine: mineBy.get(focusC.coin), starred: !!rowFor(focusC.coin) && isFav(rowFor(focusC.coin).symbol),
    onStar: toggleFav, onWatch, onClear: clear, onDetail: () => setDetail(focusC.coin), onChart: openChart,
  };
  const focusSlot = !phone && focusC
    ? <section className="smap-focus radar-focus" aria-labelledby="radar-focus-h"><FocusBody {...focusProps} titleId="radar-focus-h" /></section>
    : !focusC ? <p className="radar-hint">Tap a dot to follow one coin.</p> : null;
  // The sheet keeps showing its coin while it slides away.
  const sheetProps = useRef(null);
  if (focusProps) sheetProps.current = focusProps;
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
          <div className="smap-toggles" role="group" aria-label="Coins on the map">
            {VIEW_ITEMS.map(v => <button key={v.key} type="button" aria-pressed={(v.key === "all") === showAll} onClick={() => setParams({ view: v.key === "all" ? "all" : null })}>{v.label}</button>)}
          </div>
          <span className="radar-divider" aria-hidden="true" />
          <div className="smap-toggles" role="group" aria-label="My trades">
            <button type="button" aria-pressed={mineOn} onClick={toggleMine}>My trades</button>
          </div>
        </div>
      </div>
      {mineOn && !effectiveAddress && <div className="radar-addr-row">
        <input className="smap-addr" value={addressDraft} placeholder="Hyperliquid address (blank: executor)" aria-label="Hyperliquid address for My trades" spellCheck={false}
          onChange={e => { const v = e.target.value.trim(); setAddressDraft(v); if (isAddress(v)) setViewAddress(v); }} />
      </div>}
      {spotArrival && <p className="radar-spot-note">The Radar covers Hyperliquid perpetuals.</p>}

      <RadarPicks top={top} box={box} tf={tf} focus={focusC ? focus : null} watched={watched} inBox={inBoxN} loaded={loaded} onPick={pick} />

      <div className="radar-main">
        <RadarMap pts={pts} byCoin={byCoin} box={box} data={loaded ? data : null} tf={tf} height={mapH} focus={focusC ? focus : null} watched={watched}
          mineBy={mineBy} mineOn={mineOn} mv={mv} keep={keep} onPick={pick} />
        <RadarRail focusSlot={focusSlot} stripWatch={stripWatch} stripMine={stripMine} mineOn={mineOn} mineLoading={mineLoading}
          mv={mv} pulse={intel?.pulse} onPick={pick} />
      </div>

      {phone && <RadarSheet open={!!focusC} onClose={clear} labelledBy="radar-sheet-h">
        {sheetProps.current && <FocusBody {...sheetProps.current} titleId="radar-sheet-h" />}
      </RadarSheet>}

      {msg && <div className="smap-toast" role="status">{msg}</div>}
      {detail && detailRow && <SetupIntelDrawer row={detailRow} coin={byCoin.get(detail)} intel={intel?.coins?.[detail] || null} updatedAt={intel?.updated_at}
        watching={watched.has(detail)} onWatch={() => onWatch(detail)}
        onOpenChart={row => { setDetail(null); onSelect(row); }} onClose={() => setDetail(null)} />}
    </div>
  );
}
