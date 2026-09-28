import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import HelpTip from "../HelpTip.jsx";
import useLadder from "../../hooks/useLadder.js";
import { bandInfo, beeswarm, fmtLadderPx, fmtUsd, ladderCounts, ladderDomain, ladderRadius, logScale, niceTicks, pctText, shortAddr, spreadLabels } from "../../utils/radarDepth.js";

const TONE_COLOR = { red: "var(--rd-red)", violet: "var(--rd-inband)", halo: "inherit", none: "inherit" };

// Who is where: the followed coin's profitable wallets at their entry prices (log price axis),
// longs left and shorts right, dot area by position dollars scaled to the largest wallet in the
// coin; the price line, the weekly band shaded, the engine's mean dashed and each side's median
// entry dotted. Hover or tap a dot for the wallet. Header: coin, price, dollars held; wallets
// long and short; distance to the band. compact (the phone sheet, under the coin's own title):
// no first line.
// mark: the live mark price the followed coin's readings show, else the map's price.
export default function RadarLadder({ c, tf, mark, cardHeight, plotHeight = 420, stack = [], onPick, compact = false }) {
  const { data: lad, loading, error } = useLadder(c?.coin, tf);
  const host = useRef(null), head = useRef(null), plot = useRef(null);
  const [W, setW] = useState(360);
  const [headH, setHeadH] = useState(96);
  useEffect(() => {
    const el = host.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(([e]) => setW(Math.max(260, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  useLayoutEffect(() => { if (head.current) setHeadH(head.current.offsetHeight); });
  const [tip, setTip] = useState(null);      // {i, pinned}
  useEffect(() => setTip(null), [c?.coin, tf]);
  useEffect(() => {
    if (!tip?.pinned) return undefined;
    const off = e => { if (!plot.current?.contains(e.target)) setTip(null); };
    const esc = e => { if (e.key === "Escape") setTip(null); };
    document.addEventListener("pointerdown", off, true);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("pointerdown", off, true); document.removeEventListener("keydown", esc); };
  }, [tip?.pinned]);

  const price = mark || lad?.price || c?.price;
  const band = lad?.band ?? c?.band ?? null;
  const bi = bandInfo(band, price);
  const counts = ladderCounts(c, lad);
  const H = cardHeight ? Math.max(360, cardHeight - headH - 2) : plotHeight;

  const g = useMemo(() => {
    if (!lad || !price) return null;
    const ws = lad.positions || [];
    const R = 10, T = 26, B = 12, L = Math.max(58, fmtLadderPx(price).length * 6.8 + 14);
    const { lo, hi, lim } = ladderDomain(price, { band, mean: lad.mean, entries: ws.map(w => w.entry) });
    const Y = logScale(lo, hi, T, H - B);
    const mid = (L + W - R) / 2;
    const colL = [L + 8, mid - 6], colS = [mid + 6, W - R - 4];
    const ticks = [];
    let lastY = -99;
    for (const t of niceTicks(lo, hi, 6)) {
      const y = Y(t);
      if (Math.abs(y - Y(price)) < 16 || Math.abs(y - lastY) < 20) continue;   // clear of the price box
      lastY = y; ticks.push({ t, y });
    }
    const right = [], left = [];
    let bandRect = null;
    if (band?.lo && band?.hi) {
      const y1 = Y(band.hi), y2 = Y(band.lo);
      bandRect = { y1, y2, h: Math.max(3, y2 - y1) };
      right.push({ y: y2 + 12, t: "weekly band", col: bi.tone === "red" ? "var(--rd-red)" : "var(--rd-inband)" });
    }
    let meanY = null;
    if (lad.mean && lad.mean >= lo && lad.mean <= hi) {
      meanY = Y(lad.mean);
      // In or near the band: the word goes to the left end, clear of the band's own label.
      if (bandRect && meanY >= bandRect.y1 - 12 && meanY <= bandRect.y2 + 12) left.push({ x: L + 4, y: meanY - 4, t: "mean", col: "var(--t-text3)", anchor: "start" });
      else right.push({ y: meanY - 4, t: "mean", col: "var(--t-text3)" });
    }
    const lg = ws.filter(w => w.side === "long"), sh = ws.filter(w => w.side === "short");
    const med = [];
    const mL = lg.length ? lad.median_entry?.long : null, mS = sh.length ? lad.median_entry?.short : null;
    if (mL) { const y = Y(mL); med.push({ y, x0: colL[0] - 4, x1: colL[1] + 4, col: "var(--rd-long)" }); left.push({ x: colL[1] + 2, y: y - 4, t: "median", col: "var(--rd-long)", anchor: "end" }); }
    if (mS) { const y = Y(mS); med.push({ y, x0: colS[0] - 4, x1: colS[1] + 4, col: "var(--rd-short)" }); right.push({ y: y - 4, t: "median", col: "var(--rd-short)" }); }
    const mx = Math.max(1, ...ws.map(w => w.size_usd || 0)), dense = Math.max(lg.length, sh.length);
    const rows = (list, col, cx) => beeswarm(list.map(w => ({ w, col, y: Y(w.entry), r: ladderRadius(w.size_usd || 0, mx, { narrow: W < 360, dense }),
      off: w.entry < lim[0] || w.entry > lim[1] })), (cx[0] + cx[1]) / 2, (cx[1] - cx[0]) / 2);
    const dots = [...rows(lg, "var(--rd-long)", colL), ...rows(sh, "var(--rd-short)", colS)];
    return { ws, L, R, T, B, Y, mid, colL, colS, ticks, bandRect, meanY, med, dots, left, right: spreadLabels(right), py: Y(price) };
  }, [lad, price, band, bi.tone, W, H]);

  const d = tip && g ? g.dots[tip.i] : null;
  const tipBox = useMemo(() => {
    if (!d) return null;
    const tw = 200, th = 118;
    let x = d.x + d.r + 10;
    if (x + tw > W - 6) x = d.x - d.r - 10 - tw;
    x = Math.max(6, Math.min(W - tw - 6, x));
    const y = Math.max(4, Math.min(H - th - 4, d.y - th / 2));
    return { left: x, top: y };
  }, [d, W, H]);

  if (!c) return null;
  const held = (counts.long_usd || 0) + (counts.short_usd || 0);
  return <section className={`radar-ladder radar-mapcard${compact ? " compact" : ""}`} ref={host} aria-label={`${c.coin}: profitable wallets by entry price`}
    style={cardHeight ? { height: cardHeight } : undefined}>
    <div className="rl-head" ref={head}>
      {!compact && <div className="rl-t">
        <strong>{c.coin}</strong><span className="rl-px">{fmtLadderPx(price)}</span><span className="rl-gross">{fmtUsd(held)} held</span>
        <LadderHelp />
      </div>}
      <div className="rl-count"><span className="l">{counts.long} long {fmtUsd(counts.long_usd)}</span> · <span className="s">{counts.short} short {fmtUsd(counts.short_usd)}</span>{compact && <LadderHelp />}</div>
      <div className="rl-sub" style={{ color: TONE_COLOR[bi.tone] }}>{bi.text}</div>
      {stack.length > 0 && <div className="rl-quick"><span>Same spot</span>{stack.map(k => <button key={k} type="button" onClick={() => onPick?.(k)}>{k}</button>)}</div>}
    </div>
    <div className="rl-plot" ref={plot} style={{ height: H }}>
      {!g ? (error && !loading ? <p className="rl-empty">No wallet list right now.</p> : <div className="shimmer-loading rl-skel" aria-hidden="true" />)
        : <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${c.coin} wallets by entry price`}
          onClick={e => { if (!e.target.classList?.contains("rl-dot")) setTip(null); }}>
          <rect className="rl-col" x={g.colL[0] - 4} y={g.T - 4} width={g.colL[1] - g.colL[0] + 8} height={H - g.T - g.B + 4} rx="3" />
          <rect className="rl-col" x={g.colS[0] - 4} y={g.T - 4} width={g.colS[1] - g.colS[0] + 8} height={H - g.T - g.B + 4} rx="3" />
          <text className="rl-axl" x={(g.colL[0] + g.colL[1]) / 2} y={g.T - 10} textAnchor="middle" style={{ fill: "var(--rd-long)" }}>Long</text>
          <text className="rl-axl" x={(g.colS[0] + g.colS[1]) / 2} y={g.T - 10} textAnchor="middle" style={{ fill: "var(--rd-short)" }}>Short</text>
          {g.ticks.map(t => <g key={t.t}><line className="rl-grid" x1={g.L} x2={W - g.R} y1={t.y} y2={t.y} /><text className="rl-axt" x={g.L - 6} y={t.y + 4} textAnchor="end">{fmtLadderPx(t.t)}</text></g>)}
          {g.bandRect && <g className={`rl-band${bi.tone === "red" ? " red" : ""}`}>
            <rect x={g.L} y={g.bandRect.y1 - (g.bandRect.h === 3 ? 1.5 : 0)} width={W - g.R - g.L} height={g.bandRect.h} />
            <line x1={g.L} x2={W - g.R} y1={g.bandRect.y1} y2={g.bandRect.y1} /><line x1={g.L} x2={W - g.R} y1={g.bandRect.y2} y2={g.bandRect.y2} />
          </g>}
          {g.meanY != null && <line className="rl-mean" x1={g.L} x2={W - g.R} y1={g.meanY} y2={g.meanY} />}
          {g.med.map((m, k) => <line key={k} className="rl-med" x1={m.x0} x2={m.x1} y1={m.y} y2={m.y} style={{ stroke: m.col }} />)}
          <line className="rl-price" x1={g.L} x2={W - g.R} y1={g.py} y2={g.py} />
          <rect className="rl-pxbox" x={g.L - (fmtLadderPx(price).length * 6.8 + 8) - 2} y={g.py - 8} width={fmtLadderPx(price).length * 6.8 + 8} height="16" rx="2" />
          <text className="rl-pxt" x={g.L - 6} y={g.py + 4} textAnchor="end">{fmtLadderPx(price)}</text>
          {g.dots.map((p, i) => <circle key={`${p.w.address}${p.w.side}`} className={`rl-dot${tip?.i === i ? " on" : ""}`} cx={p.x.toFixed(1)} cy={p.y.toFixed(1)} r={p.r.toFixed(1)}
            style={{ fill: p.col }} fillOpacity={p.off ? 0.35 : 0.8} tabIndex={0} role="button"
            aria-label={`${shortAddr(p.w.address)} ${p.w.side} ${fmtUsd(p.w.size_usd)}`}
            onPointerEnter={e => { if (e.pointerType === "mouse" && !tip?.pinned) setTip({ i }); }}
            onPointerLeave={e => { if (e.pointerType === "mouse" && !tip?.pinned) setTip(null); }}
            onFocus={() => { if (!tip?.pinned) setTip({ i }); }} onBlur={() => { if (!tip?.pinned) setTip(null); }}
            onClick={e => { e.stopPropagation(); setTip(tip?.pinned && tip.i === i ? null : { i, pinned: true }); }} />)}
          {g.left.map((l, k) => <text key={`l${k}`} className="rl-line" x={l.x} y={l.y} textAnchor={l.anchor} style={{ fill: l.col }}>{l.t}</text>)}
          {g.right.map((l, k) => <text key={`r${k}`} className="rl-line" x={W - g.R - 4} y={l.y} textAnchor="end" style={{ fill: l.col }}>{l.t}</text>)}
          {!g.ws.length && <text className="rl-axl" x={g.mid} y={g.T + 40} textAnchor="middle">No profitable wallet holds {c.coin}</text>}
        </svg>}
      {d && tipBox && <div className="rl-tip" style={tipBox} role="status">
        <div className="row"><b className="m">{shortAddr(d.w.address)}</b><span style={{ color: d.col, fontWeight: 600 }}>{d.w.side === "long" ? "Long" : "Short"}</span></div>
        <div className="row"><span>Size</span><span className="m">{fmtUsd(d.w.size_usd)}{d.w.leverage ? ` · ${Math.round(d.w.leverage)}x` : ""}</span></div>
        <div className="row"><span>Entry</span><span className="m">{fmtLadderPx(d.w.entry)}</span></div>
        <div className="row"><span>Unrealised</span><span className="m" style={{ color: (d.w.upnl || 0) >= 0 ? "var(--rd-long)" : "var(--rd-short)" }}>{pctText((d.w.move || 0) / 100)} · {(d.w.upnl || 0) >= 0 ? "+" : ""}{fmtUsd(d.w.upnl || 0)}</span></div>
        {d.w.roe != null && <div className="row"><span>On margin</span><span className="m">{pctText(d.w.roe / 100, 0)}</span></div>}
      </div>}
    </div>
  </section>;
}

function LadderHelp() {
  return <HelpTip title="Who is where" width={340}>
    <p>Each dot is one profitable wallet at its entry price: longs left, shorts right. Dot area is the position in dollars, scaled to the largest wallet in this coin. Hover or tap a dot for the wallet.</p>
    <p>Solid line: price. Shaded: the coin's weekly band (20-week average and 21-week exponential average of Sunday closes). Dashed: the engine's mean. Dotted: the median entry on each side.</p>
    <p>Wallets: the Hyperliquid profitable cohort, as on the Traders page.</p>
  </HelpTip>;
}
