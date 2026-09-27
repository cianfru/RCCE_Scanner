import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import HelpTip from "./HelpTip.jsx";
import SetupIntelDrawer from "./SetupIntelDrawer.jsx";
import useSetupMap from "../hooks/useSetupMap.js";
import useMyPositions from "../hooks/useMyPositions.js";
import useSetupIntel from "../hooks/useSetupIntel.js";
import { col, getBaseSymbol } from "../theme.js";
import { fmtPx } from "../utils/traderFormat.js";
import { fmtIn, nextCloses } from "../utils/intel.js";
import { CROWD_WORD, SIGNAL_SHORT, STAGES, ZONE_WORD, at, isAddress, movement, movers, picks, pnl, symlog, trailPoints, visible, watchToast } from "../utils/setupMap.js";

const STAGE_COLOR = { forming: "#91b9e8", fresh: "#97FCE4", running: "#7d9b95", stretched: "#fbbf24", leaving: "#cf9185", waiting: "#52525b" };
const CROWD_COLOR = { quiet: "var(--t-text3)", early: "var(--t-accent)", crowded: "#fbbf24", against: "#cf9185", holding: "var(--t-text2)" };
const ZONE_COLOR = { watch: "var(--t-accent)", late: "#fbbf24", crowded: "#fbbf24", quiet: "var(--t-text3)", outside: "var(--t-text3)" };
const XS = [-2.5, 3.5];
const RM = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
const store = { get: k => { try { return localStorage.getItem(k); } catch { return null; } }, set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* private mode */ } } };
const sc = c => col(STAGE_COLOR[c.stage] || STAGE_COLOR.waiting);
const hrs = s => { const h = Math.max(0, Math.round(s / 3600)); return h < 48 ? `${h}h` : `${Math.round(h / 24)}d`; };

function Crowd({ k }) {
  return k ? <b className="smap-crowd" style={{ color: CROWD_COLOR[k] }}>{CROWD_WORD[k]}</b> : null;
}

// The coin's own trail against the box, at the map's scales.
function Thumb({ c, box }) {
  const W = 96, H = 56, ys = [symlog(-4), symlog(25)];
  const X = v => ((Math.max(XS[0], Math.min(XS[1], v)) - XS[0]) / (XS[1] - XS[0])) * W;
  const Y = v => H - ((Math.max(ys[0], Math.min(ys[1], symlog(v))) - ys[0]) / (ys[1] - ys[0])) * H;
  const p = trailPoints(c) || [{ z: c.zscore, n: (c.traders?.pl || 0) - (c.traders?.ps || 0) }];
  const e = p[p.length - 1];
  return <svg className="smap-thumb" viewBox={`0 0 ${W} ${H}`} aria-hidden="true">
    <rect x={X(box.z[0])} y={Y(box.n[1])} width={X(box.z[1]) - X(box.z[0])} height={Y(box.n[0]) - Y(box.n[1])} className="smap-box" />
    <path d={p.map((v, k) => `${k ? "L" : "M"}${X(v.z).toFixed(1)},${Y(v.n).toFixed(1)}`).join("")} fill="none" stroke={sc(c)} strokeWidth="1.6" strokeLinecap="round" strokeOpacity=".7" />
    <circle cx={X(e.z)} cy={Y(e.n)} r="3.5" fill={sc(c)} />
  </svg>;
}

function Pick({ x, box, tf, onClick }) {
  const c = x.c, t = c.transition, now = Date.now();
  const left = t ? Math.max(0, t.need - Math.min(t.seen, t.need)) : 0;
  const decides = nextCloses(tf, now, Math.max(1, c.stage === "forming" ? left : 1)).pop();
  return <button type="button" className="smap-pick" onClick={onClick}>
    <div className="smap-pick-top"><strong>{c.coin}</strong><Crowd k={c.crowd} /></div>
    <div className="smap-pick-body"><Thumb c={c} box={box} />
      <dl className="smap-kv">
        <div><dt>Signal</dt><dd>{c.stage === "forming" && t
          ? <span className="regime-progress">{Array.from({ length: t.need }, (_, k) => <i key={k} style={k < Math.min(t.seen, t.need) ? { background: STAGE_COLOR.forming, borderColor: STAGE_COLOR.forming } : { borderColor: `${STAGE_COLOR.forming}80` }} />)}</span>
          : <>{SIGNAL_SHORT[c.signal] || c.signal}{c.trigger_at ? <em> {hrs(Date.now() / 1000 - c.trigger_at)}</em> : null}</>}</dd></div>
        <div><dt>Traders</dt><dd>{c.traders?.pl || 0}{x.m?.dn > 0 ? <em className="up"> +{x.m.dn}</em> : null}</dd></div>
        <div><dt>{c.stage === "forming" ? "Decides" : "Next close"}</dt><dd>{fmtIn(decides - now).replace(/ \d+m$/, "")}</dd></div>
      </dl></div>
  </button>;
}

function StripRow({ c, mine, onClick }) {
  const r = pnl(mine, c.price);
  return <button type="button" className="smap-srow" onClick={onClick}>
    <strong>{c.coin}</strong><span style={{ color: ZONE_COLOR[c.zone] }}>{ZONE_WORD[c.zone]}</span>
    <span className="smap-mono">{SIGNAL_SHORT[c.signal] || c.signal}</span>
    {r != null && <span className="smap-mono" style={{ color: r >= 0 ? "var(--t-accent)" : "#cf9185" }}>{r >= 0 ? "+" : ""}{Math.round(100 * r)}%</span>}
  </button>;
}

function FocusChart({ c }) {
  const s = c.sparkline || [];
  if (s.length < 2) return null;
  const W = 300, H = 84, e = c.traders?.ple;
  let lo = Math.min(...s), hi = Math.max(...s);
  const showE = e && e > lo * 0.8 && e < hi * 1.2;
  if (showE) { lo = Math.min(lo, e); hi = Math.max(hi, e); }
  const x = k => (k / (s.length - 1)) * W, y = v => H - 4 - ((v - lo) / (hi - lo || 1)) * (H - 8);
  return <svg viewBox={`0 0 ${W} ${H}`} className="smap-fchart" aria-label="Recent price with the profitable traders' median entry">
    {showE && <line x1="0" x2={W} y1={y(e)} y2={y(e)} className="smap-entry" />}
    <path d={s.map((v, k) => `${k ? "L" : "M"}${x(k).toFixed(1)},${y(v).toFixed(1)}`).join("")} fill="none" stroke="var(--t-text2)" strokeWidth="1.6" />
  </svg>;
}

// Replaces the three Best setups cards: every coin placed by stretch (the engine's
// z-score) and profitable-trader lean, with trails of the last closes, a playable
// timeline, a daily shortlist, a watch list with Telegram alerts and, optionally, your
// own positions.
export default function SetupMap({ results, timeframe, onSelect }) {
  const tf = timeframe === "4h" ? "4h" : "1d";
  const [showAll, setShowAll] = useState(false);
  const [mineOn, setMineOn] = useState(() => store.get("smap-mine") === "1");
  const [address, setAddress] = useState(() => store.get("smap-address") || "");
  const [focus, setFocus] = useState(null);
  const [detail, setDetail] = useState(null);
  const [msg, setMsg] = useState("");
  const { data, watched, telegram, toggleWatch } = useSetupMap(tf);
  // My trades: the typed address, else the executor's positions; nothing while the toggle is off.
  const validAddress = isAddress(address) ? address : null;
  const { byCoin: mineBy } = useMyPositions(mineOn ? validAddress : null, { executorFallback: mineOn && !validAddress });
  const allowed = useMemo(() => new Set((results || []).map(r => r.symbol)), [results]);
  const coins = useMemo(() => (data?.coins || []).filter(c => !allowed.size || allowed.has(c.symbol)), [data, allowed]);
  const box = data?.box || { z: [-0.5, 1.5], n: [1, 8] };
  const keep = useMemo(() => new Set([...watched, ...mineBy.keys()]), [watched, mineBy]);
  const pts = useMemo(() => visible(coins, { all: showAll, keep }), [coins, showAll, keep]);
  const top = useMemo(() => picks(coins, box), [coins, box]);
  const mv = useMemo(() => movers(coins, box), [coins, box]);
  const byCoin = useMemo(() => new Map(coins.map(c => [c.coin, c])), [coins]);
  const focusC = focus && byCoin.get(focus);
  const detailRow = detail && (results || []).find(r => getBaseSymbol(r.symbol) === detail);
  const intel = useSetupIntel(detail ? [detail] : []);

  useEffect(() => { setFocus(null); }, [tf]);
  useEffect(() => { if (!msg) return undefined; const t = setTimeout(() => setMsg(""), 3500); return () => clearTimeout(t); }, [msg]);

  // ---- map: drawn by React, moved imperatively while playing
  const host = useRef(null), svgRef = useRef(null), scrub = useRef(null), when = useRef(null);
  const [W, setW] = useState(800);
  useEffect(() => {
    const el = host.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(([e]) => setW(Math.max(300, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, [results?.length > 0]);
  const small = W < 600, H = small ? 400 : 470, L = 40, R = 14, T = 16, B = 40;
  const trails = useMemo(() => new Map(pts.map(c => [c.coin, trailPoints(c)])), [pts]);
  const steps = useMemo(() => { const any = pts.find(c => c.trail?.t?.length); return any ? any.trail.t : [Date.now() / 1000]; }, [pts]);
  const last = steps.length - 1;
  const nets = pts.flatMap(c => (trails.get(c.coin) || [{ n: (c.traders?.pl || 0) - (c.traders?.ps || 0) }]).map(p => p.n));
  const ys = [symlog(Math.min(-4, ...nets)), symlog(Math.max(25, ...nets))];
  const X = useCallback(v => L + ((Math.max(XS[0], Math.min(XS[1], v)) - XS[0]) / (XS[1] - XS[0])) * (W - L - R), [W]);
  const Y = useCallback(v => T + (1 - (symlog(v) - ys[0]) / (ys[1] - ys[0])) * (H - T - B), [H, ys[0], ys[1]]);
  const u = useRef(last);
  const fmtStep = t => new Date(t * 1000).toLocaleString(undefined, tf === "1d" ? { weekday: "short", day: "numeric", month: "short" } : { weekday: "short", hour: "2-digit", minute: "2-digit" });

  const setTime = useCallback(t => {
    u.current = t;
    const svg = svgRef.current;
    if (!svg) return;
    for (const g of svg.querySelectorAll(".smap-dot")) {
      const c = byCoin.get(g.dataset.coin), p = trails.get(g.dataset.coin);
      if (!c) continue;
      const pos = p ? at(p, Math.min(t, p.length - 1)) : { z: c.zscore, n: (c.traders?.pl || 0) - (c.traders?.ps || 0) };
      const cx = X(pos.z), cy = Y(pos.n), r = +g.dataset.r;
      g.querySelector(".smap-core").setAttribute("cx", cx); g.querySelector(".smap-core").setAttribute("cy", cy);
      const ring = g.querySelector(".smap-ring"); if (ring) { ring.setAttribute("cx", cx); ring.setAttribute("cy", cy); ring.style.opacity = t >= last - 0.01 ? 1 : 0; }
      const lab = g.querySelector("text"); lab.setAttribute("x", cx + r + 4); lab.setAttribute("y", cy + 4);
      const mb = g.querySelector(".smap-minebox"); if (mb) { mb.setAttribute("x", cx - r - 5); mb.setAttribute("y", cy - r - 5); }
      const pin = g.querySelector(".smap-pin"); if (pin) pin.setAttribute("transform", `translate(${cx},${cy - r - 3})`);
      const path = g.querySelector(".smap-trail");
      if (p && path) {
        const k = Math.floor(Math.min(t, p.length - 1));
        path.setAttribute("d", "M" + [...p.slice(0, k + 1).map(v => `${X(v.z).toFixed(1)},${Y(v.n).toFixed(1)}`), `${cx.toFixed(1)},${cy.toFixed(1)}`].join("L"));
      }
    }
    const fm = svg.querySelector(".smap-focusmarks");
    if (fm) {
      const p = focus && trails.get(focus);
      fm.innerHTML = p ? p.map((v, k) => k > t + 0.01 ? "" : `<circle cx="${X(v.z)}" cy="${Y(v.n)}" r="3" fill="var(--t-text1)"/><text class="smap-stepl" x="${X(v.z) + 5}" y="${Y(v.n) - 6}">${k === p.length - 1 ? "now" : fmtStep(steps[k] - (tf === "1d" ? 86400 : 14400)).split(",")[0]}</text>`).join("") : "";
    }
    if (scrub.current && +scrub.current.value !== t) scrub.current.value = t;
    if (when.current) when.current.textContent = t >= last - 0.01 ? "Now" : `${fmtStep(steps[Math.round(t)] - (tf === "1d" ? 86400 : 14400))} close`;
  }, [byCoin, trails, X, Y, last, steps, focus, tf]);
  useEffect(() => { u.current = last; }, [last, tf]);
  useEffect(() => { setTime(Math.min(u.current, last)); }, [setTime, last, pts, W]);

  const playing = useRef(null);
  const [isPlaying, setPlaying] = useState(false);
  const stop = useCallback(() => { if (playing.current) { cancelAnimationFrame(playing.current); clearInterval(playing.current); } playing.current = null; setPlaying(false); }, []);
  const play = useCallback(() => {
    if (u.current >= last - 0.01) setTime(0);
    setPlaying(true);
    if (RM) { playing.current = setInterval(() => { const n = Math.floor(u.current) + 1; setTime(Math.min(last, n)); if (n >= last) stop(); }, 800); return; }
    const start = u.current, dur = Math.max(1, last - start) * 900; let t0 = null;
    const step = ts => { if (t0 == null) t0 = ts; const v = Math.min(last, start + ((ts - t0) / dur) * (last - start)); setTime(v);
      if (v >= last) stop(); else playing.current = requestAnimationFrame(step); };
    playing.current = requestAnimationFrame(step);
  }, [last, setTime, stop]);
  useEffect(() => stop, [stop, tf]);

  const labelled = useMemo(() => {
    const inBoxTop = pts.filter(c => c.zone === "watch").sort((a, b) => (b.priority || 0) - (a.priority || 0)).slice(0, small ? 4 : 8).map(c => c.coin);
    const big = pts.filter(c => c.zone !== "watch").sort((a, b) => Math.abs((b.traders?.pl || 0) - (b.traders?.ps || 0)) - Math.abs((a.traders?.pl || 0) - (a.traders?.ps || 0))).slice(0, small ? 2 : 5).map(c => c.coin);
    const moving = small ? [] : [...mv.entering, ...mv.leaving].map(c => c.coin);
    return new Set([...inBoxTop, ...big, ...moving, ...keep]);
  }, [pts, mv, keep, small]);

  const onWatch = async coin => setMsg(watchToast(coin, await toggleWatch(coin), telegram));
  const pick = coin => setFocus(f => (f === coin ? null : coin));

  if (!results?.length) return null;
  const stripMine = [...mineBy.values()].map(m => [byCoin.get(m.coin), m]).filter(x => x[0]);
  const stripWatch = [...watched].map(c => byCoin.get(c)).filter(Boolean);
  const mf = focusC && movement(focusC, box);
  const sg = n => `${n > 0 ? "+" : ""}${n}`;
  const past = focusC?.traders?.ple ? focusC.price / focusC.traders.ple - 1 : null;
  const myF = focusC && mineBy.get(focusC.coin);

  return <section className="smap">
    <div className="best-setups-heading"><h2>Setup map <HelpTip title="Setup map">
      <p>Each dot is a coin. Left to right: how far price sits from its mean (the engine's z-score). Bottom to top: profitable Hyperliquid traders long minus short. Colour: where the setup is (forming, just fired, running, stretched, leaving). A ring: a profitable trader opened long in the last 24 hours.</p>
      <p>Watch (the box): a setup that has not run far, with a few profitable traders long but no crowd. Stretched: late, two or more standard deviations above the mean. Trails show the last {tf === "1d" ? "5 days" : "24 hours"}; press Play to watch them move.</p>
      <p>Look at these today: coins in the box, ranked by the engine's priority plus what moved (entering the box, traders arriving, a fresh signal, a close away from confirming). A shortlist for your eyes, not a forecast: in the past these traders mostly opened after moves.</p>
    </HelpTip></h2><span>{tf.toUpperCase()}</span></div>

    {top.length > 0 && <>
      <h3 className="smap-h">Look at these today</h3>
      <div className="smap-picks">{top.map(x => <Pick key={x.c.coin} x={x} box={box} tf={tf} onClick={() => pick(x.c.coin)} />)}</div>
    </>}
    {data && !top.length && <p className="smap-note">No coin sits in the box on this timeframe right now.</p>}

    {(stripMine.length > 0 || stripWatch.length > 0) && <div className="smap-strips">
      {stripMine.length > 0 && <div className="smap-strip"><span className="smap-slab">My trades</span>{stripMine.map(([c, m]) => <StripRow key={c.coin} c={c} mine={m} onClick={() => pick(c.coin)} />)}</div>}
      {stripWatch.length > 0 && <div className="smap-strip"><span className="smap-slab">Watching</span>{stripWatch.map(c => <StripRow key={c.coin} c={c} onClick={() => pick(c.coin)} />)}</div>}
    </div>}

    <div className="smap-player">
      <button type="button" className="smap-play" onClick={() => (isPlaying ? stop() : play())} aria-label={isPlaying ? "Pause" : "Play the recent closes"}>{isPlaying ? "Pause" : "Play"}</button>
      <input ref={scrub} type="range" min="0" max={last} step="0.01" defaultValue={last} aria-label="Time" onInput={e => { stop(); setTime(+e.target.value); }} />
      <span ref={when} className="smap-when">Now</span>
      <div className="smap-toggles">
        <button type="button" aria-pressed={mineOn} onClick={() => { const v = !mineOn; setMineOn(v); store.set("smap-mine", v ? "1" : "0"); }}>My trades</button>
        <button type="button" aria-pressed={!showAll} onClick={() => setShowAll(false)}>Setups with traders</button>
        <button type="button" aria-pressed={showAll} onClick={() => setShowAll(true)}>All coins</button>
      </div>
      {mineOn && <input className="smap-addr" value={address} placeholder="Hyperliquid address (blank: executor)" aria-label="Hyperliquid address for My trades" spellCheck={false}
        onChange={e => { setAddress(e.target.value.trim()); store.set("smap-address", e.target.value.trim()); }} />}
    </div>

    <div className="smap-wrap">
      <div className="smap-mapbox" ref={host}>
        {!data ? <p className="smap-note">Loading the map…</p> :
          <svg ref={svgRef} width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Coins by stretch and profitable-trader lean">
            <rect x={X(box.z[1] + 0.5)} y={T} width={W - R - X(box.z[1] + 0.5)} height={H - B - T} className="smap-late" />
            <rect x={X(box.z[0])} y={Y(box.n[1])} width={X(box.z[1]) - X(box.z[0])} height={Y(box.n[0]) - Y(box.n[1])} className="smap-box" />
            <text className="smap-zonet" x={X(box.z[0]) + 6} y={Y(box.n[1]) + 16}>Watch</text>
            <text className="smap-regl" x={X(box.z[0]) + 6} y={Y(box.n[1]) - 10}>Crowded</text>
            <text className="smap-regl" x={X(box.z[0]) + 6} y={Y(0) + 16}>Nobody in yet</text>
            <text className="smap-regl" x={W - R - 6} y={Y(-2)} textAnchor="end">Stretched: late</text>
            {[-2, -1, 0, 1, 2, 3].map(t => <g key={`x${t}`}><line className="smap-ax" x1={X(t)} x2={X(t)} y1={T} y2={H - B} opacity=".5" /><text className="smap-axt" x={X(t)} y={H - B + 14} textAnchor="middle">{t > 0 ? "+" : ""}{t}</text></g>)}
            {[-3, 0, 1, 3, 8, 20].filter(t => symlog(t) >= ys[0] && symlog(t) <= ys[1]).map(t => <g key={`y${t}`}><line className="smap-ax" x1={L} x2={W - R} y1={Y(t)} y2={Y(t)} opacity={t === 0 ? 1 : 0.5} /><text className="smap-axt" x={L - 6} y={Y(t) + 4} textAnchor="end">{t > 0 ? "+" : ""}{t}</text></g>)}
            <text className="smap-axl" x={L} y={H - 6}>Near its mean</text><text className="smap-axl" x={W - R} y={H - 6} textAnchor="end">Stretched</text>
            <text className="smap-axl" x={L + 4} y={T + 12}>More profitable traders long</text>
            <g className="smap-focusmarks" />
            {[...pts].sort((a, b) => (a.zone === "watch") - (b.zone === "watch")).map(c => {
              const r = 4.5 + Math.min(6, Math.sqrt((c.traders?.pl || 0) + (c.traders?.ps || 0)));
              return <g key={c.coin} className={`smap-dot${focus && focus !== c.coin ? " dim" : ""}`} data-coin={c.coin} data-r={r} tabIndex={0} role="button" aria-label={c.coin}
                onClick={() => pick(c.coin)} onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(c.coin); } }}>
                <path className="smap-trail" fill="none" stroke={sc(c)} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" strokeOpacity=".55" />
                {(c.traders?.n24l || 0) > 0 && <circle className="smap-ring" r={r + 3} fill="none" stroke="var(--t-accent)" strokeWidth="1.3" />}
                <circle className="smap-core" r={r} fill={sc(c)} fillOpacity=".9" />
                {mineBy.has(c.coin) && <rect className="smap-minebox" width={2 * r + 10} height={2 * r + 10} fill="none" stroke="var(--t-text1)" strokeWidth="1.4" strokeDasharray="3 2" />}
                {watched.has(c.coin) && <path className="smap-pin" d="M-4,-7 L4,-7 L0,-1 Z" fill="var(--t-text1)" />}
                <text className="smap-lab" visibility={labelled.has(c.coin) || focus === c.coin ? "visible" : "hidden"}>{c.coin}</text>
              </g>;
            })}
          </svg>}
      </div>
      <aside className="smap-focus">
        {!focusC ? <p className="smap-note">Tap a dot to follow one coin.</p> : <>
          <div className="smap-focus-top"><h3>{focusC.coin} <span>{tf.toUpperCase()} · {fmtPx(focusC.price)}</span></h3><button type="button" className="mh-close" onClick={() => setFocus(null)}>Clear</button></div>
          <dl className="smap-kv smap-kv-rows">
            <div><dt>Setup</dt><dd style={{ color: sc(focusC) }}>{(STAGES.find(s => s.key === focusC.stage) || { name: "No setup" }).name} · {SIGNAL_SHORT[focusC.signal] || focusC.signal}</dd></div>
            <div><dt>Zone</dt><dd style={{ color: ZONE_COLOR[focusC.zone] }}>{ZONE_WORD[focusC.zone]}</dd></div>
            <div><dt>Crowd</dt><dd><Crowd k={focusC.crowd} /> {focusC.traders?.pl || 0} long · {focusC.traders?.ps || 0} short</dd></div>
            {mf && <div><dt>{tf === "1d" ? "5 days" : "24 hours"}</dt><dd>stretch {mf.p[0].z.toFixed(1)} → {mf.p[mf.p.length - 1].z.toFixed(1)} · traders {sg(mf.p[0].n)} → {sg(mf.p[mf.p.length - 1].n)}</dd></div>}
            {past != null && <div><dt>Their entry</dt><dd>{fmtPx(focusC.traders.ple)} · price {past >= 0 ? "+" : ""}{Math.round(100 * past)}%</dd></div>}
            {myF && <div><dt>Your trade</dt><dd>{myF.side} from {fmtPx(myF.entry)} · {Math.round(100 * pnl(myF, focusC.price))}%</dd></div>}
            <div><dt>Next close</dt><dd>{fmtIn(nextCloses(tf, Date.now(), 1)[0] - Date.now())}</dd></div>
          </dl>
          <FocusChart c={focusC} />
          <div className="smap-actions">
            <button type="button" className="smap-watch" aria-pressed={watched.has(focusC.coin)} onClick={() => onWatch(focusC.coin)}>{watched.has(focusC.coin) ? "Watching" : "Watch"}</button>
            <button type="button" className="te-link" onClick={() => setDetail(focusC.coin)}>Full detail</button>
            {detailRowFor(results, focusC.coin) && <button type="button" className="te-link" onClick={() => onSelect(detailRowFor(results, focusC.coin))}>Chart</button>}
          </div>
          {watched.has(focusC.coin) && <p className="smap-note">Telegram: enters the box · confirms Uptrend · turns crowded · leaves the box · exit signal</p>}
        </>}
      </aside>
    </div>

    <div className="smap-legend">{STAGES.map(s => <span key={s.key}><i style={{ background: col(STAGE_COLOR[s.key]) }} />{s.name}</span>)}<span><i className="smap-ringkey" />Opened long in 24h</span>{watched.size > 0 && <span><svg width="10" height="8" aria-hidden="true"><path d="M1,1 L9,1 L5,7 Z" fill="var(--t-text1)" /></svg>Watching</span>}</div>

    {(mv.entering.length > 0 || mv.leaving.length > 0 || mv.arriving.length > 0) && <div className="smap-movers">
      {[["Entering the box", mv.entering], ["Leaving the box", mv.leaving], ["Traders arriving", mv.arriving]].filter(([, xs]) => xs.length).map(([label, xs]) =>
        <div key={label} className="smap-strip"><span className="smap-slab">{label}</span>{xs.map(c => <button type="button" key={c.coin} className="smap-chip" onClick={() => pick(c.coin)}><strong>{c.coin}</strong><Crowd k={c.crowd} /></button>)}</div>)}
    </div>}

    {msg && <div className="smap-toast" role="status">{msg}</div>}
    {detail && detailRow && <SetupIntelDrawer row={detailRow} intel={intel?.coins?.[detail] || null} pulse={intel?.pulse}
      onOpenChart={row => { setDetail(null); onSelect(row); }} onClose={() => setDetail(null)} />}
  </section>;
}

function detailRowFor(results, coin) {
  return (results || []).find(r => getBaseSymbol(r.symbol) === coin) || null;
}
