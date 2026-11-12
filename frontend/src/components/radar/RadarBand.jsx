import { useEffect, useMemo, useRef, useState } from "react";
import HelpTip from "../HelpTip.jsx";
import TokenLogo from "../TokenLogo.jsx";
import { netFor, symlog } from "../../utils/setupMap.js";
import { bubbleRadius, fmtUsd, grossOf, maxMoney, rmaxFor, sizeFor } from "../../utils/radarDepth.js";
import { BAND_LINE, SIGNS, SIGN_WORD, xDomain, bandChanges, bandZ, clampX, crossed, heatCount, pctFromBand, placeBandLabels, trailDelta, zText } from "../../utils/radarBand.js";
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

// The map.
export function BandMap({ pts, height, focus, watched, onPick, side = "long", tf }) {
  const host = useRef(null);
  const [W, setW] = useState(800);
  const [tip, setTip] = useState(null);
  useEffect(() => {
    const el = host.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(([e]) => setW(Math.max(300, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  // Up: distance from the weekly band, so a coin sits above or below the zero line as its price sits above or
  // below the band. Right: profitable traders net long (net short in Short).
  const small = W < 600, H = height, L = 40, R = 14, T = 14, B = 40;
  const net = c => netFor(c, side);
  const nets = pts.map(net);
  const xs = [symlog(Math.min(-4, ...nets)), symlog(Math.max(side === "short" ? 10 : 25, ...nets))];
  const yd = xDomain(pts.map(bandZ));
  const size = sizeFor(side), G = maxMoney(pts, size), rmax = rmaxFor(W);
  const P = rmax + 4;                                   // the largest bubble stays inside the plot
  const X = v => L + P + ((symlog(v) - xs[0]) / (xs[1] - xs[0])) * (W - L - R - 2 * P);
  const Y = z => T + P / 2 + (1 - (clampX(z, yd) - yd[0]) / (yd[1] - yd[0])) * (H - T - B - P);
  const items = useMemo(() => pts.map(c => {
    const r = grossOf(c) > 0 ? bubbleRadius(c, G, rmax, size) : 3;
    return { c, x: X(net(c)), y: Y(bandZ(c)), r, n: heatCount(c) };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }).sort((a, b) => b.r - a.r), [pts, W, H, side, G, yd[0], yd[1]]);
  const labels = useMemo(() => placeBandLabels(items.filter(it => it.c.coin === focus || it.n >= 2 || crossed(it.c) || watched?.has(it.c.coin) || it.r >= 6 || Math.abs(net(it.c)) >= 3)
    .map(it => ({ key: it.c.coin, x: it.x, y: it.y, r: it.r, w: 8 * it.c.coin.length + 6, h: 14,
      rank: (it.c.coin === focus ? 100 : 0) + (watched?.has(it.c.coin) ? 50 : 0) + 10 * it.n + (crossed(it.c) ? 8 : 0) + it.r })), W, H, small ? 12 : 28,
    items.filter(it => it.r >= 5).map(it => ({ key: it.c.coin, x: it.x, y: it.y, r: it.r + 1 }))),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  [items, focus, watched, W, H, small]);
  const pick = c => onPick(c.coin);
  const zoneX = W - R - 8;
  return <div className="radar-mapcard rb-mapcard" ref={host}>
    <svg width={W} height={H} role="img" aria-label="Coins by distance from their weekly band and profitable-trader lean">
      <rect className="rb-under" x={L} y={Y(0)} width={W - L - R} height={H - B - Y(0)} />
      <rect className="rb-stretched" x={L} y={T} width={W - L - R} height={Math.max(0, Y(BAND_LINE) - T)} />
      {Y_TICKS.filter(t => symlog(t) >= xs[0] && symlog(t) <= xs[1] && !(small && Math.abs(t) === 1)).map(t => <g key={`x${t}`}>
        <line className="smap-ax" x1={X(t)} x2={X(t)} y1={T} y2={H - B} opacity={t === 0 ? 1 : 0.5} />
        <text className="smap-axt" x={X(t)} y={H - B + 16} textAnchor="middle">{t > 0 ? "+" : ""}{t}</text></g>)}
      {X_TICKS.filter(t => t >= yd[0] && t <= yd[1] && t !== 0 && !(Math.abs(t - BAND_LINE) < 0.5 && t !== BAND_LINE)).map(t => <text key={`y${t}`} className="smap-axt" x={L - 6} y={Y(t) + 4} textAnchor="end">{t === BAND_LINE ? "1.6" : zText(t).replace(".0", "")}</text>)}
      <line className="rb-bandline" x1={L - 4} x2={W - R} y1={Y(0)} y2={Y(0)} />
      <text className="smap-axt rb-bandtick" x={L - 6} y={Y(0) + 4} textAnchor="end">0</text>
      <line className="rb-line16" x1={L} x2={W - R} y1={Y(BAND_LINE)} y2={Y(BAND_LINE)} />
      <text className="rb-zone hot" x={zoneX} y={Y(BAND_LINE) - 7} textAnchor="end">Stretched</text>
      <text className="rb-zone" x={zoneX} y={Y(0) - 7} textAnchor="end">Above band</text>
      <text className="rb-zone" x={zoneX} y={Y(0) + 16} textAnchor="end">Under band</text>
      <text className="smap-axt" x={W - R} y={H - 6} textAnchor="end">{side === "short" ? "More profitable traders short →" : "More profitable traders long →"}</text>
      {items.map(({ c, x, y, r, n }) => <g key={c.coin} data-coin={c.coin} className={`rb-dot${focus === c.coin ? " on" : ""}`} onClick={() => pick(c)}
        onPointerEnter={() => setTip({ c, x, y, r })} onPointerLeave={() => setTip(t => (t?.c === c ? null : t))}>
        <circle cx={x} cy={y} r={r + 6} fill="transparent" />
        <circle className="rb-core" cx={x} cy={y} r={r} fill={heatVar(n)} fillOpacity={grossOf(c) > 0 ? 0.78 : 0.45}
          stroke={focus === c.coin ? "var(--t-text1)" : n >= 3 ? heatVar(n) : "none"} strokeWidth={focus === c.coin ? 2 : 1.2} />
        {crossed(c) && <circle cx={x} cy={y} r={r + 3} fill="none" stroke={crossed(c) === "up" ? "var(--rd-long)" : "var(--rd-red)"} strokeWidth={crossed(c) === "up" ? 1.4 : 1}
          strokeOpacity={crossed(c) === "up" ? 1 : 0.55} strokeDasharray="2.5 2" />}
        {watched?.has(c.coin) && <path d={`M${x - 4},${y - r - 9} L${x + 4},${y - r - 9} L${x},${y - r - 3} Z`} fill="var(--t-text1)" />}
      </g>)}
      {items.map(({ c }) => { const p = labels.get(c.coin); return p ? <text key={`l${c.coin}`} className="rb-label" x={p.x} y={p.y + 4} textAnchor={p.anchor}>{c.coin}</text> : null; })}
    </svg>
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
