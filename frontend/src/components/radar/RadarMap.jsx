import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { STAGES, at, labelBox, labelOrder, placeLabels, symlog, trailPoints } from "../../utils/setupMap.js";
import { bandInfo, bubbleRadius, candidates, countRadius, fmtUsd, grossOf, haloRing, hasMoney, legendSizes, maxMoney, rmaxFor, shortSlice, stepPick } from "../../utils/radarDepth.js";
import { Pin, RM, XS, sc, stageColor, stepLabel } from "./shared.jsx";
import HelpTip from "../HelpTip.jsx";

const TONE = { red: "var(--rd-red)", violet: "var(--rd-inband)", halo: "var(--rd-halo)" };
const net = c => (c.traders?.pl || 0) - (c.traders?.ps || 0);

// A small ring for the legend: fill share f of the band halo, in a colour, with the red tick.
function Ring({ f = 0, color, tick }) {
  const C = 2 * Math.PI * 6;
  return <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" style={{ overflow: "visible" }}>
    <circle cx="8" cy="8" r="6" fill="none" stroke="var(--rd-track)" strokeWidth="2" />
    {f > 0 && <circle cx="8" cy="8" r="6" fill="none" stroke={color} strokeWidth="2" strokeDasharray={`${f * C} ${C}`} transform="rotate(-90 8 8)" />}
    {tick && <line x1="8" x2="8" y1="-1" y2="4" stroke="var(--rd-red)" strokeWidth="2" strokeLinecap="round" />}
  </svg>;
}

// The Radar's map: every coin placed by stretch (the engine's z-score) and profitable-trader
// lean, with trails of the last closes and a playable timeline. Bubble area is the dollars the
// profitable wallets hold in the coin (a pink slice for the short share; a small grey dot when
// none hold it), and a ring tracks the distance to the coin's weekly band. Drawn by React,
// moved imperatively while playing (behind Replay). The key sits behind an (i). A click picks the nearest centre and steps through coins
// stacked at one spot. Labels: the coins with the most money, placed without collisions at rest
// and again at each close the timeline passes; between two closes every label keeps its side.
export default function RadarMap({ pts, byCoin, box, data, tf, height, focus, watched, mineBy, mineOn, keep, onPick, onRest, moneyOn = true }) {
  const host = useRef(null), svgRef = useRef(null), scrub = useRef(null), when = useRef(null), tipRef = useRef(null);
  const [W, setW] = useState(800);
  useEffect(() => {
    const el = host.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(([e]) => setW(Math.max(300, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const small = W < 600, H = height, L = 40, R = 14, T = 16, B = 40;
  const trails = useMemo(() => new Map(pts.map(c => [c.coin, trailPoints(c)])), [pts]);
  const steps = useMemo(() => { const any = pts.find(c => c.trail?.t?.length); return any ? any.trail.t : [Date.now() / 1000]; }, [pts]);
  const last = steps.length - 1;
  const nets = pts.flatMap(c => (trails.get(c.coin) || [{ n: net(c) }]).map(p => p.n));
  // A little headroom on top for the largest bubbles.
  const ys = [symlog(Math.min(-4, ...nets)), symlog(Math.max(25, ...nets)) + (moneyOn ? 0.06 : 0)];
  const X = useCallback(v => L + ((Math.max(XS[0], Math.min(XS[1], v)) - XS[0]) / (XS[1] - XS[0])) * (W - L - R), [W]);
  const Y = useCallback(v => T + (1 - (symlog(v) - ys[0]) / (ys[1] - ys[0])) * (H - T - B), [H, ys[0], ys[1]]);
  const u = useRef(last);
  const dt = tf === "1d" ? 86400 : 14400;
  const fmtStep = t => stepLabel(t, tf);

  // Sizes and rings: one money scale for the map and its key.
  const G = useMemo(() => maxMoney(pts), [pts]);
  const rmax = rmaxFor(W);
  const geo = useMemo(() => new Map(pts.map(c => {
    const r = moneyOn ? bubbleRadius(c, G, rmax) : countRadius(c);
    const empty = moneyOn && !hasMoney(c);
    const bi = moneyOn && !empty ? bandInfo(c.band, c.price) : null;
    const ring = bi ? haloRing(r, bi) : null;
    return [c.coin, { r, empty, bi, ring, outer: ring ? Math.max(r, ring.outer) : r, slice: moneyOn && !empty ? shortSlice(r, c.money?.net_long_share) : null }];
  })), [pts, G, rmax, moneyOn]);

  const byMoney = useMemo(() => [...pts].filter(hasMoney).sort((a, b) => grossOf(b) - grossOf(a)), [pts]);
  // At rest, trails show for the eight coins with the most money, the followed and the hovered
  // coin; while the timeline plays or is scrubbed, every trail shows.
  const trailed = useMemo(() => new Set(moneyOn ? byMoney.slice(0, 8).map(c => c.coin) : pts.map(c => c.coin)), [byMoney, pts, moneyOn]);
  const labelled = useMemo(() => {
    if (moneyOn) return new Set([...byMoney.slice(0, small ? 4 : 12).map(c => c.coin), ...keep]);
    const inBoxTop = pts.filter(c => c.zone === "watch").sort((a, b) => (b.priority || 0) - (a.priority || 0)).slice(0, small ? 4 : 8).map(c => c.coin);
    const big = pts.filter(c => c.zone !== "watch").sort((a, b) => Math.abs(net(b)) - Math.abs(net(a))).slice(0, small ? 2 : 5).map(c => c.coin);
    return new Set([...inBoxTop, ...big, ...keep]);
  }, [pts, byMoney, keep, small, moneyOn]);
  // Always shown while the trails move (on their right when they had no room at the last placement).
  const pinned = useMemo(() => new Set([...(focus ? [focus] : []), ...watched, ...mineBy.keys()]), [focus, watched, mineBy]);
  const order = useMemo(() => {
    if (!moneyOn) return labelOrder(pts, { labelled, focus, watched, mine: new Set(mineBy.keys()) });
    const rank = c => (c.coin === focus ? 0 : watched.has(c.coin) ? 1 : mineBy.has(c.coin) ? 2 : 3);
    return pts.filter(c => c.coin === focus || labelled.has(c.coin)).sort((a, b) => rank(a) - rank(b) || grossOf(b) - grossOf(a) || a.coin.localeCompare(b.coin));
  }, [pts, labelled, focus, watched, mineBy, moneyOn]);
  // Drawing order: largest first, so a smaller bubble sits on a larger one (ETH over BTC); at
  // equal size, coins in the box on top. Following a coin never changes the order.
  const painted = useMemo(() => {
    const lift = c => (c.zone === "watch" ? 1 : 0);
    return [...pts].sort((a, b) => (geo.get(b.coin)?.r || 0) - (geo.get(a.coin)?.r || 0) || lift(a) - lift(b));
  }, [pts, geo]);
  const under = useMemo(() => { const k = new Map(painted.map((c, i) => [c.coin, i])); return (d, o) => (k.get(o.coin) ?? -1) < (k.get(d.coin) ?? -1); }, [painted]);

  // Dated marks on the followed coin's trail up to step t; newest first, so a later date
  // never hides "now". Each takes the first of above right, above left, below right and
  // below left that clears the marks already drawn and the followed coin's own label.
  const drawMarks = useCallback((t, keepClear) => {
    const fm = svgRef.current?.querySelector(".smap-focusmarks");
    if (!fm) return;
    const p = focus && trails.get(focus);
    const R = +(fm.parentNode.querySelector(".smap-dot.on")?.dataset.o || 3);
    const dots = [], texts = [], taken = keepClear ? [keepClear] : [];
    const here = p && p.length ? at(p, Math.min(t, p.length - 1)) : null, hx = here ? X(here.z) : 0, hy = here ? Y(here.n) : 0;
    for (let k = p ? p.length - 1 : -1; k >= 0; k--) {
      if (k > t + 0.01) continue;
      const x = X(p[k].z), y = Y(p[k].n), now = k === p.length - 1, s = now ? "now" : tf === "1d" ? stepLabel(steps[k] - dt, tf).split(" ")[0] : stepLabel(steps[k] - dt, tf);
      // A bubble larger than a dot is its own "now"; marks it covers are left out.
      if (now ? R > 8 : Math.hypot(x - hx, y - hy) < R + 2) continue;
      if (!now) dots.push(`<circle cx="${x}" cy="${y}" r="3" fill="var(--t-text1)"/>`);
      const w = 6.2 * s.length + 2;
      // "now" sits on the coin's own bubble, so it clears that bubble's ring; older marks sit on 3px dots.
      const ox = now ? Math.max(7, 0.72 * R + 3) : 7, up = now ? Math.max(6, 0.72 * R + 1) : 6, down = now ? 0.72 * R + 10 : 14;
      const spot = [[x + ox, y - up, "start"], [x - ox, y - up, "end"], [x + ox, y + down, "start"], [x - ox, y + down, "end"]].map(([tx, ty, a]) =>
        ({ tx, ty, a, b: { x0: a === "start" ? tx - 2 : tx - w, x1: a === "start" ? tx + w : tx + 2, y0: ty - 10, y1: ty + 4 } }))
        .find(({ b }) => !taken.some(o => b.x0 < o.x1 && o.x0 < b.x1 && b.y0 < o.y1 && o.y0 < b.y1));
      if (!spot) continue;
      taken.push(spot.b);
      texts.push(`<text class="smap-stepl" x="${spot.tx}" y="${spot.ty}"${spot.a === "end" ? ' text-anchor="end"' : ""}>${s}</text>`);
    }
    fm.innerHTML = dots.join("") + texts.join("");
  }, [focus, trails, X, Y, steps, dt, tf]);

  // Labels: placed without collisions at rest, when the dot set or the size changes, when the
  // scrubber is released and each time the timeline passes a close. In between (playing or
  // scrubbing), every label keeps the side it was given and follows its dot. The followed
  // coin's label always shows: it is placed first, its dated marks keep clear of it, and every
  // other label keeps clear of both. A big bubble whose name fits carries it inside.
  const sides = useRef(new Map());   // coin -> {dx, dy, anchor, inside} from the last placement
  const placedStep = useRef(null);
  const posRef = useRef(new Map());
  const layoutLabels = useCallback((pos, place, t) => {
    const svg = svgRef.current;
    if (!svg) return;
    const labs = new Map([...svg.querySelectorAll(".smap-dot")].map(g => [g.dataset.coin, g.querySelector(".smap-lab")]));
    const right = p => ({ x: p.x + p.r + 4, y: p.y + 4, anchor: "start" });
    const follow = (coin, p) => { const s = sides.current.get(coin); return s ? { x: p.x + s.dx, y: p.y + s.dy, anchor: s.anchor, inside: s.inside } : null; };
    const bbox = el => { try { const b = el.getBBox(); return { x0: b.x - 1, y0: b.y - 1, x1: b.x + b.width + 1, y1: b.y + b.height + 1 }; } catch { return null; } };
    const widthOf = coin => { const el = labs.get(coin); try { const w = el?.getComputedTextLength(); return w ? w + 4 : 0; } catch { return 0; } };
    const bounds = { x0: L, y0: 0, x1: W, y1: H - B };
    const fixed = place ? [...svg.querySelectorAll(".smap-zonet,.smap-regl,.smap-axl")].map(bbox).filter(Boolean) : [];
    const insideMin = moneyOn ? 13 : Infinity;
    const fp = focus && pos.get(focus);
    let fAt = null;
    if (fp && place) {
      const others = [...pos].filter(([coin]) => coin !== focus).map(([coin, p]) => ({ coin, ...p }));
      fAt = placeLabels([{ coin: focus, ...fp }], { bounds, widthOf, others, avoid: fixed, force: focus, insideMin }).get(focus);
    } else if (fp) fAt = follow(focus, fp) || right(fp);
    const fBox = fAt ? labelBox(fAt.x, fAt.y, fAt.anchor, widthOf(focus) || 6.4 * focus.length + 4) : null;
    drawMarks(t, fBox);
    let placed = null;
    if (place) {
      const dots = order.filter(c => c.coin !== focus).map(c => pos.get(c.coin) && { coin: c.coin, ...pos.get(c.coin) }).filter(Boolean);
      const inOrder = new Set(dots.map(d => d.coin));
      const others = [...pos].filter(([coin]) => !inOrder.has(coin)).map(([coin, p]) => ({ coin, ...p }));
      const marks = [...svg.querySelectorAll(".smap-stepl")].map(bbox).filter(Boolean);
      placed = placeLabels(dots, { bounds, widthOf, others, avoid: [...fixed, ...marks, ...(fBox ? [fBox] : [])], relax: small, under, insideMin });
      if (fAt) placed.set(focus, fAt);
      sides.current = new Map([...placed].map(([coin, a]) => { const p = pos.get(coin); return [coin, { dx: a.x - p.x, dy: a.y - p.y, anchor: a.anchor, inside: !!a.inside }]; }));
    }
    for (const [coin, lab] of labs) {
      const p = pos.get(coin);
      if (!lab || !p) continue;
      // Between placements: the kept side; a pinned coin (focused, watched, mine) that had no
      // room at the last placement still shows, on its right. A hidden label still moves with
      // its dot (on its right), for hover and focus.
      const at_ = coin === focus ? fAt : place ? placed.get(coin) : (follow(coin, p) || (pinned.has(coin) ? right(p) : null));
      const spot = at_ || right(p);
      lab.setAttribute("x", spot.x); lab.setAttribute("y", spot.y); lab.setAttribute("text-anchor", spot.anchor);
      lab.classList.toggle("off", !at_);
      lab.classList.toggle("in", !!spot.inside);
    }
  }, [order, pinned, focus, drawMarks, small, under, W, H, moneyOn]);

  // t: the timeline position (0 .. last); settle: place the labels afresh now.
  const setTime = useCallback((t, settle = false) => {
    u.current = t;
    const svg = svgRef.current;
    if (!svg) return;
    const pos = new Map();
    const rest = t >= last - 0.01;
    for (const g of svg.querySelectorAll(".smap-dot")) {
      const c = byCoin.get(g.dataset.coin), p = trails.get(g.dataset.coin), gm = geo.get(g.dataset.coin);
      if (!c || !gm) continue;
      const q = p ? at(p, Math.min(t, p.length - 1)) : { z: c.zscore, n: net(c) };
      const cx = X(q.z), cy = Y(q.n);
      // The ring reads today's price against the band: shown only at "now".
      const r = rest ? gm.outer : gm.r;
      pos.set(c.coin, { x: cx, y: cy, r, core: gm.r, empty: gm.empty });
      g.querySelector(".smap-body").setAttribute("transform", `translate(${cx.toFixed(1)},${cy.toFixed(1)})`);
      for (const h of g.querySelectorAll(".smap-halo")) h.style.opacity = rest ? 1 : 0;
      const path = g.querySelector(".smap-trail");
      if (p && path) {
        const k = Math.floor(Math.min(t, p.length - 1));
        path.setAttribute("d", "M" + [...p.slice(0, k + 1).map(v => `${X(v.z).toFixed(1)},${Y(v.n).toFixed(1)}`), `${cx.toFixed(1)},${cy.toFixed(1)}`].join("L"));
      }
    }
    posRef.current = pos;
    host.current?.classList.toggle("moving", !rest);
    const step = rest ? last : Math.floor(t + 1e-6);
    const place = settle || rest || step !== placedStep.current;
    if (place) placedStep.current = step;
    layoutLabels(pos, place, t);
    if (place && rest) onRest?.(pos);
    if (scrub.current && +scrub.current.value !== t) scrub.current.value = t;
    if (when.current) when.current.textContent = rest ? "Now" : `${fmtStep(steps[Math.round(t)] - dt)} close`;
  }, [byCoin, trails, geo, X, Y, last, steps, tf, layoutLabels, onRest]);
  useEffect(() => { u.current = last; }, [last, tf]);
  // A new dot set (sector, view, my trades, data) or size: the labels are placed afresh,
  // wherever the timeline stands.
  useLayoutEffect(() => { setTime(Math.min(u.current, last), true); }, [setTime, last, pts, W, H]);
  // Real text widths once the fonts are in.
  useEffect(() => { document.fonts?.ready?.then(() => setTime(u.current, true)).catch(() => {}); }, [setTime]);

  const playing = useRef(null);
  const [isPlaying, setPlaying] = useState(false);
  // The timeline is one click away: Replay opens the player, Close returns the map to now.
  const [replay, setReplay] = useState(false);
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
  const closeReplay = () => { stop(); setReplay(false); setTime(last, true); };

  // Releasing the scrubber settles the labels where the trails stopped.
  useEffect(() => {
    const el = scrub.current;
    if (!el) return undefined;
    const settle = () => setTime(u.current, true);
    el.addEventListener("change", settle);
    el.addEventListener("pointerup", settle);
    return () => { el.removeEventListener("change", settle); el.removeEventListener("pointerup", settle); };
  }, [setTime, data, replay]);

  // Picking: the nearest centre (a small bubble over a big one wins), and a click on the same
  // spot again steps to the next coin stacked there. A mouse hover shows the coin's card.
  const [hover, setHover] = useState(null);     // {coin, list}
  const lastPick = useRef(null);
  const items = () => [...posRef.current].map(([coin, p]) => ({ coin, x: p.x, y: p.y, r: p.core, empty: p.empty }));
  const at_ = e => { const rc = svgRef.current.getBoundingClientRect(); return [e.clientX - rc.left, e.clientY - rc.top]; };
  const onMove = e => {
    if (e.pointerType !== "mouse" || !svgRef.current) return;
    const [px, py] = at_(e), list = candidates(items(), px, py, { small });
    const top = list[0]?.coin || null;
    if (top !== hover?.coin) setHover(top ? { coin: top, list: list.map(i => i.coin) } : null);
  };
  const onClick = e => {
    if (!svgRef.current) return;
    const touch = e.nativeEvent?.pointerType ? e.nativeEvent.pointerType !== "mouse" : window.matchMedia?.("(pointer:coarse)").matches;
    const [px, py] = at_(e), list = candidates(items(), px, py, { small, touch });
    if (!list.length) { lastPick.current = null; return; }
    if (list.length === 1) { lastPick.current = null; onPick(list[0].coin); return; }   // one coin: follow it, or let it go
    const s = stepPick(list, px, py, lastPick.current, focus);
    lastPick.current = s.last;
    if (s.coin !== focus) onPick(s.coin);
    if (!touch) setHover({ coin: s.coin, list: list.map(i => i.coin) });
  };
  useEffect(() => { lastPick.current = null; }, [pts, W, H]);
  // Keep the hover card beside its bubble, inside the map.
  useLayoutEffect(() => {
    const tip = tipRef.current, p = hover && posRef.current.get(hover.coin);
    if (!tip || !p) return;
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    let x = p.x + p.r + 14, y = p.y - th / 2;
    if (x + tw > W - 6) x = p.x - p.r - 14 - tw;
    if (x < 6) { x = Math.max(6, Math.min(W - tw - 6, p.x - tw / 2)); y = p.y + p.r + 12; }
    if (y + th > H - 6) y = p.y - p.r - 12 - th;
    tip.style.left = `${x}px`; tip.style.top = `${Math.max(6, Math.min(H - th - 6, y))}px`;
  }, [hover, W, H]);
  const hc = hover && byCoin.get(hover.coin);
  const hStack = hover && hc ? (() => { const me = posRef.current.get(hover.coin); return hover.list.filter(k => k !== hover.coin && me && posRef.current.get(k) && Math.hypot(posRef.current.get(k).x - me.x, posRef.current.get(k).y - me.y) < 6); })() : [];

  // Day ticks under the scrubber, one per close ("Mon", "Tue" ...). The latest close carries
  // no word: the readout beside the scrubber already says "Now".
  const tickLabel = k => (k === last ? "" : tf === "1d" ? stepLabel(steps[k] - dt, tf).split(" ")[0] : stepLabel(steps[k] - dt, "4h").split(" ")[1]);
  const sparse = last > 0 && (W - 200) / (last + 1) < 46;
  const sizes = moneyOn ? legendSizes(G, rmax) : [];

  return <div className="radar-mapcol">
    <div className="radar-mapcard">
      <div className="smap-mapbox" ref={host} style={{ minHeight: H }} onPointerLeave={() => setHover(null)}>
        {!data ? <div className="radar-map-loading shimmer-loading" style={{ height: H }} aria-label="Loading the map" /> :
          <svg ref={svgRef} width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Coins by stretch and profitable-trader lean"
            className={hover ? "pick" : undefined} onPointerMove={onMove} onClick={onClick}>
            <rect x={X(box.z[1] + 0.5)} y={T} width={W - R - X(box.z[1] + 0.5)} height={H - B - T} className="smap-late" />
            <rect x={X(box.z[0])} y={Y(box.n[1])} width={X(box.z[1]) - X(box.z[0])} height={Y(box.n[0]) - Y(box.n[1])} className="smap-box" />
            {[-2, -1, 0, 1, 2, 3].map(t => <g key={`x${t}`}><line className="smap-ax" x1={X(t)} x2={X(t)} y1={T} y2={H - B} opacity=".5" /><text className="smap-axt" x={X(t)} y={H - B + 14} textAnchor="middle">{t > 0 ? "+" : ""}{t}</text></g>)}
            {[-3, 0, 1, 3, 8, 20, 50].filter(t => symlog(t) >= ys[0] && symlog(t) <= ys[1]).map(t => <g key={`y${t}`}><line className="smap-ax" x1={L} x2={W - R} y1={Y(t)} y2={Y(t)} opacity={t === 0 ? 1 : 0.5} /><text className="smap-axt" x={L - 6} y={Y(t) + 4} textAnchor="end">{t > 0 ? "+" : ""}{t}</text></g>)}
            <g className="smap-focusmarks" />
            {painted.map(c => {
              const gm = geo.get(c.coin), r = gm.r, ring = gm.ring, on = focus === c.coin, big = r >= 12, col = gm.empty ? "var(--t-text3)" : sc(c);
              return <g key={c.coin} className={`smap-dot${focus && !on ? " dim" : ""}${on ? " on" : ""}${hover?.coin === c.coin ? " hov" : ""}${gm.empty ? " empty" : ""}${trailed.has(c.coin) ? "" : " minor"}`} data-coin={c.coin} data-r={r} data-o={gm.outer}
                tabIndex={0} role="button" aria-label={c.coin} aria-pressed={on}
                onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPick(c.coin); } }}>
                <path className="smap-trail" fill="none" stroke={sc(c)} strokeWidth={on ? 2 : 1.4} strokeLinecap="round" strokeLinejoin="round" strokeOpacity={on ? 0.9 : gm.empty ? 0.18 : 0.35} />
                <g className="smap-body">
                  {!moneyOn && (c.traders?.n24l || 0) > 0 && <circle className="smap-halo" r={r + 3} fill="none" stroke="var(--t-accent)" strokeWidth="1.3" />}
                  {ring?.show && <g className="smap-halo">
                    {ring.track && <circle r={ring.hr} fill="none" stroke="var(--rd-track)" strokeWidth={ring.sw} />}
                    {ring.arc > 0 && <circle r={ring.hr} fill="none" stroke={TONE[gm.bi.tone]} strokeWidth={ring.sw} strokeDasharray={`${ring.arc.toFixed(2)} ${ring.C.toFixed(2)}`} transform="rotate(-90)" />}
                    {ring.tick && <line x1="0" x2="0" y1={-ring.hr - 3} y2={-ring.hr + 2.5} stroke="var(--rd-red)" strokeWidth="2" strokeLinecap="round" />}
                  </g>}
                  <circle className="smap-core" r={r} fill={col} fillOpacity={gm.empty ? 0.55 : moneyOn && big ? 0.58 : 0.9} strokeWidth={big ? 1.5 : 1} />
                  {gm.slice && <path className="smap-slice" d={gm.slice} fill="var(--rd-short)" fillOpacity={big ? 0.55 : 0.85} />}
                  {on && <circle className="smap-sel" r={(gm.outer + 3.5).toFixed(2)} fill="none" />}
                  {mineBy.has(c.coin) && <rect className="smap-minebox" x={-gm.outer - 5} y={-gm.outer - 5} width={2 * gm.outer + 10} height={2 * gm.outer + 10} fill="none" stroke="var(--t-text1)" strokeWidth="1.4" strokeDasharray="3 2" />}
                  {watched.has(c.coin) && <path className="smap-pin" transform={`translate(0,${-gm.outer - 3})`} d="M-4,-7 L4,-7 L0,-1 Z" fill="var(--t-text1)" />}
                </g>
                <text className="smap-lab off">{c.coin}</text>
              </g>;
            })}
            {/* The plot's own captions sit above the dots, cut out of them by a halo in the page colour. */}
            <g className="smap-captions" aria-hidden="true">
              <text className="smap-zonet" x={X(box.z[0]) + 6} y={Y(box.n[1]) + 16}>Early setups</text>
              <text className="smap-regl smap-latet" x={W - R - 6} y={H - B - 8} textAnchor="end">Stretched</text>
              <text className="smap-axl" x={L} y={H - 6}>Near its mean</text><text className="smap-axl" x={W - R} y={H - 6} textAnchor="end">Stretched</text>
              <text className="smap-axl" x={L + 4} y={T + 12}>More profitable traders long</text>
            </g>
          </svg>}
        {hc && <div className="smap-tip" ref={tipRef} role="status">
          <div className="row"><b>{hc.coin}</b><span style={{ color: sc(hc), fontWeight: 600 }}>{(STAGES.find(s => s.key === hc.stage) || { name: "No setup" }).name}</span></div>
          {moneyOn && <div className="row"><span>Held</span><span className="m">{fmtUsd(grossOf(hc))}{grossOf(hc) ? ` · ${Math.round(100 * (hc.money.net_long_share ?? 1))}% long` : ""}</span></div>}
          {moneyOn && <div className="row"><span>Band</span><span className="m" style={{ color: { red: "var(--rd-red)", violet: "var(--rd-inband)" }[bandInfo(hc.band, hc.price).tone] }}>{bandInfo(hc.band, hc.price).short}</span></div>}
          <div className="row"><span>Wallets</span><span className="m">{hc.traders?.pl || 0} long · {hc.traders?.ps || 0} short</span></div>
          {hStack.length > 0 && <div className="also">Also here: {hStack.join(", ")}. Click again to step.</div>}
        </div>}
      </div>
      <div className={`smap-player radar-player${replay ? "" : " closed"}`}>
        {replay ? <>
          <button type="button" className="smap-play" onClick={() => (isPlaying ? stop() : play())} aria-label={isPlaying ? "Pause" : "Play the recent closes"}>{isPlaying ? "Pause" : "Play"}</button>
          <div className="radar-scrub">
            <input ref={scrub} type="range" min="0" max={last} step="0.01" defaultValue={u.current} aria-label="Time" onInput={e => { stop(); setTime(+e.target.value); }} />
            {last > 0 && <div className={`radar-ticks${sparse ? " sparse" : ""}`} aria-hidden="true">
              {steps.map((s, k) => <span key={s} style={{ left: `calc(8px + (100% - 16px) * ${k / last})` }}>{tickLabel(k)}</span>)}
            </div>}
          </div>
          <span ref={when} className="smap-when">Now</span>
          <button type="button" className="mh-close radar-replay-close" onClick={closeReplay}>Close</button>
        </> : <button type="button" className="te-link radar-replay" disabled={!data || last < 1} onClick={() => setReplay(true)}>Replay</button>}
        <HelpTip title="Map key" width={360} className="radar-keytip" label="Map key">
          <div className="radar-key smap-legend radar-legend">
            <div className="grp">{STAGES.map(s => <span key={s.key}><i style={{ background: stageColor(s.key) }} />{s.name}</span>)}</div>
            {moneyOn ? <>
              <div className="grp">
                {sizes.map(s => <span key={s.v}><svg width={2 * s.r + 2} height={2 * s.r + 2} aria-hidden="true"><circle cx={s.r + 1} cy={s.r + 1} r={s.r} fill="none" stroke="var(--t-text3)" /></svg>{fmtUsd(s.v)}</span>)}
                <span><svg width="14" height="14" aria-hidden="true"><circle cx="7" cy="7" r="6" fill={stageColor("running")} /><path d="M7,7 L7,1 A6,6 0 0 1 12.7,5.1 Z" fill="var(--rd-short)" fillOpacity=".85" /></svg>short</span>
              </div>
              <div className="grp">
                <span><Ring f={0.5} color="var(--rd-halo)" />near band</span>
                <span><Ring f={1} color="var(--rd-inband)" />in band</span>
                <span><Ring f={1} color="var(--rd-red)" />closed under</span>
              </div>
            </> : <div className="grp"><span><i className="smap-ringkey" />Opened long in 24h</span></div>}
            {(watched.size > 0 || mineOn) && <div className="grp">
              {watched.size > 0 && <span><Pin />Watching</span>}
              {mineOn && <span><i className="radar-minekey" />My trade</span>}
            </div>}
          </div>
          <p>Size: the dollars profitable traders hold, longs plus shorts; the pink slice is the short share. A small grey dot: none hold it.</p>
          <p>Ring: the distance to the coin's weekly band (20-week average and 21-week exponential average of Sunday closes). Empty at 30% or more above it, full at its top edge. Violet: inside the band. Red: the last weekly close ended under it.</p>
        </HelpTip>
      </div>
    </div>
  </div>;
}
