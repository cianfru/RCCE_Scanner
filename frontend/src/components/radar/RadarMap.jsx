import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { col } from "../../theme.js";
import { STAGES, at, labelOrder, placeLabels, symlog, trailPoints } from "../../utils/setupMap.js";
import { Pin, RM, STAGE_COLOR, XS, sc } from "./shared.jsx";

// The Radar's map: every coin placed by stretch (the engine's z-score) and profitable-trader
// lean, with trails of the last closes and a playable timeline. Drawn by React, moved
// imperatively while playing. Labels are placed without collisions at rest; while playing or
// scrubbing only the focused, watched and mine labels show.
export default function RadarMap({ pts, byCoin, box, data, tf, height, focus, watched, mineBy, mineOn, mv, keep, onPick }) {
  const host = useRef(null), svgRef = useRef(null), scrub = useRef(null), when = useRef(null);
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
  const nets = pts.flatMap(c => (trails.get(c.coin) || [{ n: (c.traders?.pl || 0) - (c.traders?.ps || 0) }]).map(p => p.n));
  const ys = [symlog(Math.min(-4, ...nets)), symlog(Math.max(25, ...nets))];
  const X = useCallback(v => L + ((Math.max(XS[0], Math.min(XS[1], v)) - XS[0]) / (XS[1] - XS[0])) * (W - L - R), [W]);
  const Y = useCallback(v => T + (1 - (symlog(v) - ys[0]) / (ys[1] - ys[0])) * (H - T - B), [H, ys[0], ys[1]]);
  const u = useRef(last);
  const dt = tf === "1d" ? 86400 : 14400;
  const fmtStep = t => new Date(t * 1000).toLocaleString(undefined, tf === "1d" ? { weekday: "short", day: "numeric", month: "short" } : { weekday: "short", hour: "2-digit", minute: "2-digit" });

  const labelled = useMemo(() => {
    const inBoxTop = pts.filter(c => c.zone === "watch").sort((a, b) => (b.priority || 0) - (a.priority || 0)).slice(0, small ? 4 : 8).map(c => c.coin);
    const big = pts.filter(c => c.zone !== "watch").sort((a, b) => Math.abs((b.traders?.pl || 0) - (b.traders?.ps || 0)) - Math.abs((a.traders?.pl || 0) - (a.traders?.ps || 0))).slice(0, small ? 2 : 5).map(c => c.coin);
    const moving = small ? [] : [...mv.entering, ...mv.leaving].map(c => c.coin);
    return { all: new Set([...inBoxTop, ...big, ...moving, ...keep]), movers: new Set(moving.filter(c => !big.includes(c))) };
  }, [pts, mv, keep, small]);
  // Always shown, placed on the right, even while the trails move.
  const pinned = useMemo(() => new Set([...(focus ? [focus] : []), ...watched, ...mineBy.keys()]), [focus, watched, mineBy]);
  const order = useMemo(() => labelOrder(pts, { labelled: labelled.all, focus, watched, mine: new Set(mineBy.keys()), movers: labelled.movers }),
    [pts, labelled, focus, watched, mineBy]);

  // Labels: at rest, the collision-free layout; in motion, only the pinned ones on the right.
  const layoutLabels = useCallback((pos, full) => {
    const svg = svgRef.current;
    if (!svg) return;
    const labs = new Map([...svg.querySelectorAll(".smap-dot")].map(g => [g.dataset.coin, g.querySelector(".smap-lab")]));
    const right = (lab, p) => { lab.setAttribute("x", p.x + p.r + 4); lab.setAttribute("y", p.y + 4); lab.setAttribute("text-anchor", "start"); };
    let placed = null;
    if (full) {
      const dots = order.map(c => pos.get(c.coin) && { coin: c.coin, ...pos.get(c.coin) }).filter(Boolean);
      const inOrder = new Set(dots.map(d => d.coin));
      const others = [...pos].filter(([coin]) => !inOrder.has(coin)).map(([coin, p]) => ({ coin, ...p }));
      const avoid = [...svg.querySelectorAll(".smap-zonet,.smap-regl,.smap-axl,.smap-stepl")].map(el => {
        try { const b = el.getBBox(); return { x0: b.x - 1, y0: b.y - 1, x1: b.x + b.width + 1, y1: b.y + b.height + 1 }; } catch { return null; }
      }).filter(Boolean);
      const widthOf = coin => { const el = labs.get(coin); try { const w = el?.getComputedTextLength(); return w ? w + 4 : 0; } catch { return 0; } };
      placed = placeLabels(dots, { bounds: { x0: L, y0: 0, x1: W, y1: H - B }, widthOf, others, avoid });
    }
    for (const [coin, lab] of labs) {
      const p = pos.get(coin);
      if (!lab || !p) continue;
      const at_ = placed?.get(coin);
      if (at_) { lab.setAttribute("x", at_.x); lab.setAttribute("y", at_.y); lab.setAttribute("text-anchor", at_.anchor); }
      else right(lab, p);
      lab.classList.toggle("off", full ? !at_ : !pinned.has(coin));
    }
  }, [order, pinned, W, H]);

  const setTime = useCallback(t => {
    u.current = t;
    const svg = svgRef.current;
    if (!svg) return;
    const pos = new Map();
    for (const g of svg.querySelectorAll(".smap-dot")) {
      const c = byCoin.get(g.dataset.coin), p = trails.get(g.dataset.coin);
      if (!c) continue;
      const q = p ? at(p, Math.min(t, p.length - 1)) : { z: c.zscore, n: (c.traders?.pl || 0) - (c.traders?.ps || 0) };
      const cx = X(q.z), cy = Y(q.n), r = +g.dataset.r;
      pos.set(c.coin, { x: cx, y: cy, r });
      g.querySelector(".smap-core").setAttribute("cx", cx); g.querySelector(".smap-core").setAttribute("cy", cy);
      const ring = g.querySelector(".smap-ring"); if (ring) { ring.setAttribute("cx", cx); ring.setAttribute("cy", cy); ring.style.opacity = t >= last - 0.01 ? 1 : 0; }
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
      // Dated marks on the followed coin's trail; newest first, so a later date never hides "now".
      const p = focus && trails.get(focus);
      const dots = [], texts = [], taken = [];
      for (let k = p ? p.length - 1 : -1; k >= 0; k--) {
        if (k > t + 0.01) continue;
        const x = X(p[k].z), y = Y(p[k].n), s = k === p.length - 1 ? "now" : fmtStep(steps[k] - dt).split(",")[0];
        dots.push(`<circle cx="${x}" cy="${y}" r="3" fill="var(--t-text1)"/>`);
        const b = { x0: x + 5, x1: x + 9 + 6.2 * s.length, y0: y - 16, y1: y - 2 };
        if (taken.some(o => b.x0 < o.x1 && o.x0 < b.x1 && b.y0 < o.y1 && o.y0 < b.y1)) continue;
        taken.push(b);
        texts.push(`<text class="smap-stepl" x="${x + 7}" y="${y - 6}">${s}</text>`);
      }
      fm.innerHTML = dots.join("") + texts.join("");
    }
    layoutLabels(pos, t >= last - 0.01);
    if (scrub.current && +scrub.current.value !== t) scrub.current.value = t;
    if (when.current) when.current.textContent = t >= last - 0.01 ? "Now" : `${fmtStep(steps[Math.round(t)] - dt)} close`;
  }, [byCoin, trails, X, Y, last, steps, focus, tf, layoutLabels]);
  useEffect(() => { u.current = last; }, [last, tf]);
  useLayoutEffect(() => { setTime(Math.min(u.current, last)); }, [setTime, last, pts, W, H]);
  // Real text widths once the fonts are in.
  useEffect(() => { document.fonts?.ready?.then(() => setTime(u.current)).catch(() => {}); }, [setTime]);

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

  // Releasing the scrubber settles the labels where the trails stopped.
  useEffect(() => {
    const el = scrub.current;
    if (!el) return undefined;
    const settle = () => {
      const svg = svgRef.current;
      if (!svg) return;
      const pos = new Map();
      for (const g of svg.querySelectorAll(".smap-dot")) {
        const core = g.querySelector(".smap-core");
        pos.set(g.dataset.coin, { x: +core.getAttribute("cx"), y: +core.getAttribute("cy"), r: +g.dataset.r });
      }
      layoutLabels(pos, true);
    };
    el.addEventListener("change", settle);
    el.addEventListener("pointerup", settle);
    return () => { el.removeEventListener("change", settle); el.removeEventListener("pointerup", settle); };
  }, [layoutLabels, data]);

  // Day ticks under the scrubber, one per close ("Mon" ... "now").
  const tickLabel = k => (k === last ? "now" : tf === "1d"
    ? new Date((steps[k] - dt) * 1000).toLocaleString(undefined, { weekday: "short" })
    : new Date((steps[k] - dt) * 1000).toLocaleString(undefined, { hour: "2-digit", minute: "2-digit" }));
  const sparse = last > 0 && (W - 200) / (last + 1) < 46;

  return <div className="radar-mapcard">
    <div className="smap-legend radar-legend">
      {STAGES.map(s => <span key={s.key}><i style={{ background: col(STAGE_COLOR[s.key]) }} />{s.name}</span>)}
      <span><i className="smap-ringkey" />Opened long in 24h</span>
      <span><Pin />Watching</span>
      {mineOn && <span><i className="radar-minekey" />My trade</span>}
    </div>
    <div className="smap-mapbox" ref={host} style={{ minHeight: H }}>
      {!data ? <div className="radar-map-loading shimmer-loading" style={{ height: H }} aria-label="Loading the map" /> :
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
            return <g key={c.coin} className={`smap-dot${focus && focus !== c.coin ? " dim" : ""}${focus === c.coin ? " on" : ""}`} data-coin={c.coin} data-r={r} tabIndex={0} role="button" aria-label={c.coin}
              aria-pressed={focus === c.coin} onClick={() => onPick(c.coin)} onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPick(c.coin); } }}>
              <path className="smap-trail" fill="none" stroke={sc(c)} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" strokeOpacity=".55" />
              {(c.traders?.n24l || 0) > 0 && <circle className="smap-ring" r={r + 3} fill="none" stroke="var(--t-accent)" strokeWidth="1.3" />}
              <circle className="smap-core" r={r} fill={sc(c)} fillOpacity=".9" />
              {mineBy.has(c.coin) && <rect className="smap-minebox" width={2 * r + 10} height={2 * r + 10} fill="none" stroke="var(--t-text1)" strokeWidth="1.4" strokeDasharray="3 2" />}
              {watched.has(c.coin) && <path className="smap-pin" d="M-4,-7 L4,-7 L0,-1 Z" fill="var(--t-text1)" />}
              <text className="smap-lab off">{c.coin}</text>
            </g>;
          })}
        </svg>}
    </div>
    <div className="smap-player radar-player">
      <button type="button" className="smap-play" onClick={() => (isPlaying ? stop() : play())} aria-label={isPlaying ? "Pause" : "Play the recent closes"}>{isPlaying ? "Pause" : "Play"}</button>
      <div className="radar-scrub">
        <input ref={scrub} type="range" min="0" max={last} step="0.01" defaultValue={last} aria-label="Time" onInput={e => { stop(); setTime(+e.target.value); }} />
        {last > 0 && <div className={`radar-ticks${sparse ? " sparse" : ""}`} aria-hidden="true">
          {steps.map((s, k) => <span key={s} style={{ left: `calc(8px + (100% - 16px) * ${k / last})` }}>{tickLabel(k)}</span>)}
        </div>}
      </div>
      <span ref={when} className="smap-when">Now</span>
    </div>
  </div>;
}

