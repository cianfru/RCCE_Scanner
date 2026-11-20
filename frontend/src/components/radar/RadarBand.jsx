import { useEffect, useMemo, useRef, useState } from "react";
import HelpTip from "../HelpTip.jsx";
import TokenLogo from "../TokenLogo.jsx";
import { netFor, symlog } from "../../utils/setupMap.js";
import { bubbleRadius, fmtUsd, grossOf, maxMoney, rmaxFor, sizeFor } from "../../utils/radarDepth.js";
import { BAND_LINE, MAX_ZOOM, SIGNS, SIGN_WORD, VIEW0, panBy, pinch, xDomain, zoomAt, bandChanges, bandZ, clampX, crossed, heatCount, pctFromBand, placeBandLabels, trailDelta, zText } from "../../utils/radarBand.js";
import { Pin } from "./shared.jsx";

// Radar, band view: every coin placed by how far it sits from its own weekly band (band z) and by
// profitable-trader lean, coloured by how many of four heat signs are lit. Above it, what changed this week.
// Context, not a signal.

const heatVar = n => `var(--rh-${Math.max(0, Math.min(4, n))})`;
const Y_TICKS = [-50, -20, -8, -3, 0, 1, 3, 8, 20, 50];
const X_TICKS = [-3, -2, -1, 0, 1, BAND_LINE, 2, 3, 4];

// Four small squares, one per sign: filled when lit, outlined when not, dashed when there is no reading.
export function Signs({ c, size = 8 }) {
  return <span className="rb-signs" aria-label={`${heatCount(c)} of 4 heat signs`}>
    {SIGNS.map(k => { const v = c?.heat_signs?.[k]; return <i key={k} title={SIGN_WORD[k]} className={v === true ? "on" : v == null ? "na" : ""}
      style={{ width: size, height: size, ...(v === true ? { background: heatVar(heatCount(c)), borderColor: heatVar(heatCount(c)) } : null) }} />; })}
  </span>;
}

function HeatKey() {
  return <span className="rb-key">{[0, 1, 2, 3, 4].map(n => <span key={n}><i style={{ background: heatVar(n) }} />{n}</span>)}</span>;
}

export function AboutBand({ tf }) {
  return <HelpTip title="Reading the band view">
    <p>Up and down: how far price sits above or below the coin's weekly bull market support band (20-week SMA and 21-week EMA), scaled to how far that coin usually sits from it over two years. 0 is the band; the 1.6 line is where the stretch study put a coin's top 5% of days.</p>
    <p>Left to right: profitable Hyperliquid traders long minus short. Size: their dollars in the coin.</p>
    <p>Colour: how many of four heat signs are lit. {SIGNS.map(k => SIGN_WORD[k]).join("; ")}. Far above its band: 1.6 or more. Heat engine hot: heat 40 or more on the way up, or its exhaustion phase. Funding crowded long: over 0.01% an hour. Traders: crowded, or 2 or more fewer net long over the last {tf === "1d" ? "5 days" : "24 hours"}.</p>
    <p>What changed: coins that crossed their band in the last 7 days, traders arriving, and coins with 3 or 4 signs lit. Context, not a signal.</p>
  </HelpTip>;
}

function Row({ c, value, onPick, focus, watched }) {
  return <li><button type="button" className="rb-row" aria-pressed={focus === c.coin} onClick={() => onPick(c.coin)}>
    <span className="rb-coin"><TokenLogo symbol={c.symbol} size={16} />{c.coin}{watched?.has(c.coin) && <Pin size={7} title="Watching" />}</span>
    <span className="rb-val">{value}</span>
  </button></li>;
}

// What changed: four short lists.
export function BandChanges({ coins, tf, loaded, focus, watched, onPick }) {
  const ch = useMemo(() => bandChanges(coins), [coins]);
  const cols = [
    { k: "up", title: "Crossed above band", sub: "7d", val: c => zText(bandZ(c)) },
    { k: "down", title: "Fell below band", sub: "7d", val: c => zText(bandZ(c)) },
    { k: "arriving", title: "Traders arriving", sub: tf === "1d" ? "5d" : "24h", val: c => `+${trailDelta(c)}` },
    { k: "hot", title: "Hot", sub: "3+ signs", val: c => <Signs c={c} /> },
  ];
  return <section className="rb-changes" aria-labelledby="rb-changes-h">
    <div className="radar-picks-head"><h2 id="rb-changes-h">What changed <AboutBand tf={tf} /></h2></div>
    <div className="rb-cols">{cols.map(col => <div key={col.k} className="rb-col">
      <h3>{col.title} <em>{col.sub}</em></h3>
      {!loaded ? <div className="rb-skel shimmer-loading" aria-hidden="true" />
        : ch[col.k].length ? <ul>{ch[col.k].map(c => <Row key={c.coin} c={c} value={col.val(c)} onPick={onPick} focus={focus} watched={watched} />)}</ul>
          : <p className="rb-none">None</p>}
    </div>)}</div>
  </section>;
}

// Zoom controls: in, out and back to the whole map (shown once zoomed).
function ZoomButtons({ k, onIn, onOut, onReset }) {
  return <div className="rb-zoom" role="group" aria-label="Zoom">
    <button type="button" onClick={onIn} aria-label="Zoom in" disabled={k >= MAX_ZOOM}>+</button>
    <button type="button" onClick={onOut} aria-label="Zoom out" disabled={k <= 1}>−</button>
    {k > 1 && <button type="button" className="rb-zoom-reset" onClick={onReset}>Reset</button>}
  </div>;
}

// The map. Pinch (touch or trackpad) or Ctrl/Cmd + scroll zooms around the fingers or pointer; once zoomed, a
// drag moves the map. Bubbles and labels keep their size, so close coins separate as you zoom.
export function BandMap({ pts, height, focus, watched, onPick, side = "long", tf }) {
  const host = useRef(null), svgRef = useRef(null);
  const [W, setW] = useState(800);
  const [tip, setTip] = useState(null);
  const [view, setView] = useState(VIEW0);
  useEffect(() => {
    const el = host.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(([e]) => setW(Math.max(300, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  useEffect(() => setView(VIEW0), [tf, side, W, height]);
  // Up: distance from the weekly band, so a coin sits above or below the zero line as its price sits above or
  // below the band. Right: profitable traders net long (net short in Short).
  const small = W < 600, H = height, L = 40, R = 14, T = 14, B = 40;
  const box = useMemo(() => ({ x0: L, x1: W - R, y0: T, y1: H - B }), [W, H]);
  const boxRef = useRef(box); boxRef.current = box;
  const viewRef = useRef(view); viewRef.current = view;
  const net = c => netFor(c, side);
  const nets = pts.map(net);
  const xs = [symlog(Math.min(-4, ...nets)), symlog(Math.max(side === "short" ? 10 : 25, ...nets))];
  const yd = xDomain(pts.map(bandZ));
  const size = sizeFor(side), G = maxMoney(pts, size), rmax = rmaxFor(W);
  const P = rmax + 4;                                   // the largest bubble stays inside the plot
  const X0 = v => L + P + ((symlog(v) - xs[0]) / (xs[1] - xs[0])) * (W - L - R - 2 * P);
  const Y0 = z => T + P / 2 + (1 - (clampX(z, yd) - yd[0]) / (yd[1] - yd[0])) * (H - T - B - P);
  const X = v => view.tx + view.k * X0(v);
  const Y = z => view.ty + view.k * Y0(z);
  const inX = x => x >= box.x0 - 0.5 && x <= box.x1 + 0.5, inY = y => y >= box.y0 - 0.5 && y <= box.y1 + 0.5;
  const items = useMemo(() => pts.map(c => {
    const r = grossOf(c) > 0 ? bubbleRadius(c, G, rmax, size) : 3;
    return { c, x: X(net(c)), y: Y(bandZ(c)), r, n: heatCount(c) };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }).sort((a, b) => b.r - a.r), [pts, W, H, side, G, yd[0], yd[1], view]);
  const shown = useMemo(() => items.filter(it => it.x + it.r >= box.x0 && it.x - it.r <= box.x1 && it.y + it.r >= box.y0 && it.y - it.r <= box.y1), [items, box]);
  const labels = useMemo(() => placeBandLabels(shown.filter(it => view.k > 1.5 || it.c.coin === focus || it.n >= 2 || crossed(it.c) || watched?.has(it.c.coin) || it.r >= 6 || Math.abs(net(it.c)) >= 3)
    .map(it => ({ key: it.c.coin, x: it.x, y: it.y, r: it.r, w: 8 * it.c.coin.length + 6, h: 14,
      rank: (it.c.coin === focus ? 100 : 0) + (watched?.has(it.c.coin) ? 50 : 0) + 10 * it.n + (crossed(it.c) ? 8 : 0) + it.r })), W, H,
    Math.round((small ? 12 : 28) * Math.min(3, view.k)),
    shown.filter(it => it.r >= 5).map(it => ({ key: it.c.coin, x: it.x, y: it.y, r: it.r + 1 }))),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  [shown, focus, watched, W, H, small, view.k]);

  // ---- gestures
  const gest = useRef({ pts: new Map(), start: null, moved: false });
  const restart = () => { const g = gest.current; g.start = { view: viewRef.current, pts: new Map(g.pts) }; };
  const local = e => { const r = svgRef.current.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return undefined;
    const wheel = e => {                               // trackpad pinch (Chrome, Firefox, Edge) and Ctrl/Cmd + scroll
      if (!(e.ctrlKey || e.metaKey)) return;
      e.preventDefault();
      const p = local(e);
      const dy = Math.max(-30, Math.min(30, e.deltaY * (e.deltaMode === 1 ? 5 : 1)));   // a mouse notch is about 1.35x; trackpad pinches are smooth
      setView(v => zoomAt(v, v.k * Math.exp(-dy * 0.01), p.x, p.y, boxRef.current));
      setTip(null);
    };
    let g0 = null;                                     // Safari trackpad pinch
    const gs = e => { e.preventDefault(); g0 = { k: viewRef.current.k, p: local(e) }; };
    const gc = e => { e.preventDefault(); if (g0) setView(v => zoomAt(v, g0.k * e.scale, g0.p.x, g0.p.y, boxRef.current)); };
    const tm = e => { if (e.touches.length >= 2 || viewRef.current.k > 1) e.preventDefault(); };   // keep the page still
    el.addEventListener("wheel", wheel, { passive: false });
    el.addEventListener("gesturestart", gs);
    el.addEventListener("gesturechange", gc);
    el.addEventListener("touchmove", tm, { passive: false });
    return () => {
      el.removeEventListener("wheel", wheel);
      el.removeEventListener("gesturestart", gs);
      el.removeEventListener("gesturechange", gc);
      el.removeEventListener("touchmove", tm);
    };
  }, []);
  const onPointerDown = e => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    const g = gest.current;
    if (g.pts.size === 0) g.moved = false;
    g.pts.set(e.pointerId, local(e));
    restart();
    if (g.pts.size > 1) setTip(null);
    if (g.pts.size !== 1) return;
    const move = ev => {
      if (!g.pts.has(ev.pointerId)) return;
      g.pts.set(ev.pointerId, local(ev));
      const s = g.start;
      if (g.pts.size >= 2) {
        const [a, b] = [...g.pts.values()], [a0, b0] = [...s.pts.values()];
        if (!a0 || !b0) return;
        const d = Math.hypot(a.x - b.x, a.y - b.y), d0 = Math.hypot(a0.x - b0.x, a0.y - b0.y);
        g.moved = true;
        setView(pinch(s.view, d0, { x: (a0.x + b0.x) / 2, y: (a0.y + b0.y) / 2 }, d, { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }, boxRef.current));
      } else if (s.view.k > 1) {
        const p = g.pts.get(ev.pointerId), p0 = s.pts.get(ev.pointerId);
        if (!p0) return;
        if (!g.moved && Math.hypot(p.x - p0.x, p.y - p0.y) < 4) return;
        g.moved = true;
        setTip(null);
        setView(panBy(s.view, p.x - p0.x, p.y - p0.y, boxRef.current));
      }
    };
    const up = ev => {
      g.pts.delete(ev.pointerId);
      restart();
      if (g.pts.size === 0) {
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
        window.removeEventListener("pointercancel", up);
      }
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
  };
  const zoomBy = f => setView(v => zoomAt(v, v.k * f, (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2, box));
  const pick = c => { if (!gest.current.moved) onPick(c.coin); };
  const zoneX = W - R - 8;
  const yLine = (y, el) => (inY(y) ? el : null);
  const xTicks = Y_TICKS.filter(t => symlog(t) >= xs[0] && symlog(t) <= xs[1] && !(small && view.k < 1.5 && Math.abs(t) === 1)).filter(t => inX(X(t)));
  const yTicks = X_TICKS.filter(t => t >= yd[0] && t <= yd[1] && t !== 0 && !(view.k < 1.5 && Math.abs(t - BAND_LINE) < 0.5 && t !== BAND_LINE)).filter(t => inY(Y(t)));
  const y0 = Y(0), y16 = Y(BAND_LINE);
  const clipId = `rbclip-${tf}-${side}`;
  return <div className="radar-mapcard rb-mapcard" ref={host}>
    <svg ref={svgRef} width={W} height={H} role="img" aria-label="Coins by distance from their weekly band and profitable-trader lean"
      className={`rb-svg${view.k > 1 ? " zoomed" : ""}`} onPointerDown={onPointerDown}>
      <defs><clipPath id={clipId}><rect x={box.x0} y={box.y0} width={box.x1 - box.x0} height={box.y1 - box.y0} /></clipPath></defs>
      <g clipPath={`url(#${clipId})`}>
        <rect className="rb-under" x={L} y={Math.max(box.y0, y0)} width={W - L - R} height={Math.max(0, box.y1 - Math.max(box.y0, y0))} />
        <rect className="rb-stretched" x={L} y={T} width={W - L - R} height={Math.max(0, Math.min(box.y1, y16) - T)} />
        {xTicks.map(t => <line key={`xl${t}`} className="smap-ax" x1={X(t)} x2={X(t)} y1={T} y2={H - B} opacity={t === 0 ? 1 : 0.5} />)}
        <line className="rb-bandline" x1={L - 4} x2={W - R} y1={y0} y2={y0} />
        <line className="rb-line16" x1={L} x2={W - R} y1={y16} y2={y16} />
        {yLine(y16 - 7, <text className="rb-zone hot" x={zoneX} y={y16 - 7} textAnchor="end">Stretched</text>)}
        {yLine(y0 - 7, <text className="rb-zone" x={zoneX} y={y0 - 7} textAnchor="end">Above band</text>)}
        {yLine(y0 + 16, <text className="rb-zone" x={zoneX} y={y0 + 16} textAnchor="end">Under band</text>)}
        {shown.map(({ c, x, y, r, n }) => <g key={c.coin} data-coin={c.coin} className={`rb-dot${focus === c.coin ? " on" : ""}`} onClick={() => pick(c)}
          onPointerEnter={e => { if (e.pointerType === "mouse" && gest.current.pts.size === 0) setTip({ c, x, y, r }); }} onPointerLeave={() => setTip(t => (t?.c === c ? null : t))}>
          <circle cx={x} cy={y} r={r + 6} fill="transparent" />
          <circle className="rb-core" cx={x} cy={y} r={r} fill={heatVar(n)} fillOpacity={grossOf(c) > 0 ? 0.78 : 0.45}
            stroke={focus === c.coin ? "var(--t-text1)" : n >= 3 ? heatVar(n) : "none"} strokeWidth={focus === c.coin ? 2 : 1.2} />
          {crossed(c) && <circle cx={x} cy={y} r={r + 3} fill="none" stroke={crossed(c) === "up" ? "var(--rd-long)" : "var(--rd-red)"} strokeWidth={crossed(c) === "up" ? 1.4 : 1}
            strokeOpacity={crossed(c) === "up" ? 1 : 0.55} strokeDasharray="2.5 2" />}
          {watched?.has(c.coin) && <path d={`M${x - 4},${y - r - 9} L${x + 4},${y - r - 9} L${x},${y - r - 3} Z`} fill="var(--t-text1)" />}
        </g>)}
        {shown.map(({ c }) => { const p = labels.get(c.coin); return p ? <text key={`l${c.coin}`} className="rb-label" x={p.x} y={p.y + 4} textAnchor={p.anchor}>{c.coin}</text> : null; })}
      </g>
      {xTicks.map(t => <text key={`xt${t}`} className="smap-axt" x={X(t)} y={H - B + 16} textAnchor="middle">{t > 0 ? "+" : ""}{t}</text>)}
      {yTicks.map(t => <text key={`y${t}`} className="smap-axt" x={L - 6} y={Y(t) + 4} textAnchor="end">{t === BAND_LINE ? "1.6" : zText(t).replace(".0", "")}</text>)}
      {yLine(y0, <text className="smap-axt rb-bandtick" x={L - 6} y={y0 + 4} textAnchor="end">0</text>)}
      <text className="smap-axt" x={W - R} y={H - 6} textAnchor="end">{side === "short" ? "More profitable traders short →" : "More profitable traders long →"}</text>
    </svg>
    <ZoomButtons k={view.k} onIn={() => zoomBy(1.6)} onOut={() => zoomBy(1 / 1.6)} onReset={() => setView(VIEW0)} />
    {tip && <div className="rb-tip" style={{ left: tip.x + tip.r + 230 < W ? tip.x + tip.r + 10 : Math.max(4, tip.x - tip.r - 222),
      top: Math.max(4, Math.min(H - 190, tip.y - 20)), "--tipc": heatVar(heatCount(tip.c)) }} role="tooltip">
      <strong>{tip.c.coin}</strong>
      <div>Band {zText(bandZ(tip.c))} <em>{pctFromBand(tip.c.band_z?.pct)} from mid</em></div>
      <div>Traders {tip.c.traders?.pl || 0} long · {tip.c.traders?.ps || 0} short{grossOf(tip.c) > 0 ? ` · ${fmtUsd(grossOf(tip.c))}` : ""}</div>
      <ul>{SIGNS.map(k => <li key={k} className={tip.c.heat_signs?.[k] === true ? "on" : ""}>{SIGN_WORD[k]}{tip.c.heat_signs?.[k] == null ? ": no reading" : ""}</li>)}</ul>
    </div>}
    <div className="rb-foot"><span>Heat signs lit <HeatKey /></span><span className="rb-foot-r"><i className="rb-ring up" />Crossed up <i className="rb-ring down" />Fell below <em>{tf === "1d" ? "1D" : "4H"} traders · daily band</em></span></div>
  </div>;
}
