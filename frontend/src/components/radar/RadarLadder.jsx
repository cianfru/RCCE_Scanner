import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import HelpTip from "../HelpTip.jsx";
import WalletTag, { WalletAvatar } from "../WalletTag.jsx";
import useLadder from "../../hooks/useLadder.js";
import { nameIn, shortAddr, viewNames } from "../../utils/walletName.js";
import { trendNote } from "../../utils/chartPresentation.js";
import { bandInfo, beeswarm, entryNote, fmtLadderPx, fmtUsd, ladderCounts, ladderDomain, ladderRadius, logScale, niceTicks, pctText, spreadLabels, topWallets, traderPath, walletPnl } from "../../utils/radarDepth.js";

const TONE_COLOR = { red: "var(--rd-red)", violet: "var(--rd-inband)", halo: "inherit", none: "inherit" };

// Who is where: the followed coin's profitable wallets at their entry prices (log price axis),
// longs left and shorts right, dot area by position dollars scaled to the largest wallet in the
// coin; the price line, the weekly band shaded, the engine's trend line dashed and each side's median
// entry dotted, and the dollar-weighted average long entry dashed ("avg entry", the entry zone's
// reference). Hover or focus a dot for the wallet; a click (or Enter) opens the trader's
// profile. On touch the first tap shows the wallet with an "Open profile" link, a second tap
// on the same dot opens it. Header: coin, price, dollars held; wallets
// long and short; distance to the band. compact (the phone sheet, under the coin's own title):
// no first line.
// mark: the live mark price the followed coin's readings show, else the map's price.
// side: the map's Long · Short · Both; in Short the header's counts lead with the shorts.
export default function RadarLadder({ c, tf, mark, cardHeight, plotHeight = 420, stack = [], onPick, compact = false, side = "long" }) {
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
  const [tip, setTip] = useState(null);      // {i, pinned, via: "mouse" | "key" | "touch"}
  const ptr = useRef(null);                  // how the last dot press came: "mouse", "touch", "pen" or "key"
  const navigate = useNavigate();
  const openProfile = useCallback((address, e) => {
    const href = traderPath(address);
    if (e && (e.metaKey || e.ctrlKey || e.shiftKey)) window.open(href, "_blank", "noopener");
    else navigate(href);
  }, [navigate]);
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
  const entry = lad?.entry ?? c?.entry ?? null;
  const note = entryNote(entry, counts.long);
  const H = cardHeight ? Math.max(360, cardHeight - headH - 2) : plotHeight;

  const g = useMemo(() => {
    if (!lad || !price) return null;
    const ws = lad.positions || [];
    const R = 10, T = 26, B = 12, L = Math.max(58, fmtLadderPx(price).length * 6.8 + 14);
    const { lo, hi, lim } = ladderDomain(price, { band, trend: lad.trend, entries: ws.map(w => w.entry) });
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
    let trendY = null;
    if (lad.trend && lad.trend >= lo && lad.trend <= hi) {
      trendY = Y(lad.trend);
      // In or near the band: the word goes to the left end, clear of the band's own label.
      if (bandRect && trendY >= bandRect.y1 - 12 && trendY <= bandRect.y2 + 12) left.push({ x: L + 4, y: trendY - 4, t: "trend", col: "var(--t-text3)", anchor: "start" });
      else right.push({ y: trendY - 4, t: "trend", col: "var(--t-text3)" });
    }
    const lg = ws.filter(w => w.side === "long"), sh = ws.filter(w => w.side === "short");
    const med = [];
    const mL = lg.length ? lad.median_entry?.long : null, mS = sh.length ? lad.median_entry?.short : null;
    if (mL) { const y = Y(mL); med.push({ y, x0: colL[0] - 4, x1: colL[1] + 4, col: "var(--rd-long)" }); left.push({ x: colL[1] + 2, y: y - 4, t: "median", col: "var(--rd-long)", anchor: "end" }); }
    if (mS) { const y = Y(mS); med.push({ y, x0: colS[0] - 4, x1: colS[1] + 4, col: "var(--rd-short)" }); right.push({ y: y - 4, t: "median", col: "var(--rd-short)" }); }
    // The profitable traders' dollar-weighted average long entry: dashed across the plot, word on the right.
    let avgY = null;
    const avg = lg.length ? entry?.avg_long_entry : null;
    if (avg && avg >= lo && avg <= hi) { avgY = Y(avg); right.push({ y: avgY - 4, t: "avg entry", col: "var(--rd-long)" }); }
    const mx = Math.max(1, ...ws.map(w => w.size_usd || 0)), dense = Math.max(lg.length, sh.length);
    const rows = (list, col, cx) => beeswarm(list.map(w => ({ w, col, y: Y(w.entry), r: ladderRadius(w.size_usd || 0, mx, { narrow: W < 360, dense }),
      off: w.entry < lim[0] || w.entry > lim[1] })), (cx[0] + cx[1]) / 2, (cx[1] - cx[0]) / 2);
    const dots = [...rows(lg, "var(--rd-long)", colL), ...rows(sh, "var(--rd-short)", colS)];
    return { ws, L, R, T, B, Y, mid, colL, colS, ticks, bandRect, trendY, avgY, med, dots, left, right: spreadLabels(right), py: Y(price) };
  }, [lad, price, band, bi.tone, W, H, entry?.avg_long_entry]);

  const names = useMemo(() => viewNames((g?.ws || []).map(w => w.address)), [g]);
  const d = tip && g ? g.dots[tip.i] : null;
  const tipBox = useMemo(() => {
    if (!d) return null;
    // Beside the dot when the card fits either side, else above or below it (the phone's narrow
    // ladder), so a pinned card never covers the dot it belongs to.
    const tw = 216, th = 170, gap = d.r + 10;
    const clampX = v => Math.max(6, Math.min(W - tw - 6, v));
    if (d.x + gap + tw <= W - 6 || d.x - gap - tw >= 6) {
      const x = d.x + gap + tw <= W - 6 ? d.x + gap : d.x - gap - tw;
      return { left: x, top: Math.max(4, Math.min(H - th - 4, d.y - th / 2)) };
    }
    return { left: clampX(d.x - tw / 2), top: d.y - gap - th >= 4 ? d.y - gap - th : d.y + gap };
  }, [d, W, H]);

  if (!c) return null;
  const held = (counts.long_usd || 0) + (counts.short_usd || 0);
  return <section className={`radar-ladder radar-mapcard${compact ? " compact" : ""}`} ref={host} aria-label={`${c.coin}: profitable traders by entry price`}
    style={cardHeight ? { height: cardHeight } : undefined}>
    <div className="rl-head" ref={head}>
      {!compact && <div className="rl-t">
        <strong>{c.coin}</strong><span className="rl-px">{fmtLadderPx(price)}</span><span className="rl-gross">{fmtUsd(held)} held</span>
        <LadderHelp tf={tf} />
      </div>}
      <div className="rl-count">{side === "short"
        ? <><span className="s">{counts.short} short {fmtUsd(counts.short_usd)}</span> · <span className="l">{counts.long} long {fmtUsd(counts.long_usd)}</span></>
        : <><span className="l">{counts.long} long {fmtUsd(counts.long_usd)}</span> · <span className="s">{counts.short} short {fmtUsd(counts.short_usd)}</span></>}{compact && <LadderHelp tf={tf} />}</div>
      <div className="rl-sub"><span style={{ color: TONE_COLOR[bi.tone] }}>{bi.text}</span>{note && <span className={entry?.in_zone ? "rl-ez" : undefined}>{` · ${note}`}</span>}</div>
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
          {g.trendY != null && <line className="rl-trend" x1={g.L} x2={W - g.R} y1={g.trendY} y2={g.trendY} />}
          {g.avgY != null && <line className="rl-avg" x1={g.L} x2={W - g.R} y1={g.avgY} y2={g.avgY} />}
          {g.med.map((m, k) => <line key={k} className="rl-med" x1={m.x0} x2={m.x1} y1={m.y} y2={m.y} style={{ stroke: m.col }} />)}
          <line className="rl-price" x1={g.L} x2={W - g.R} y1={g.py} y2={g.py} />
          <rect className="rl-pxbox" x={g.L - (fmtLadderPx(price).length * 6.8 + 8) - 2} y={g.py - 8} width={fmtLadderPx(price).length * 6.8 + 8} height="16" rx="2" />
          <text className="rl-pxt" x={g.L - 6} y={g.py + 4} textAnchor="end">{fmtLadderPx(price)}</text>
          {g.dots.map((p, i) => <circle key={`${p.w.address}${p.w.side}`} className={`rl-dot${tip?.i === i ? " on" : ""}`} cx={p.x.toFixed(1)} cy={p.y.toFixed(1)} r={p.r.toFixed(1)}
            style={{ fill: p.col }} fillOpacity={p.off ? 0.35 : 0.8} tabIndex={0} role="link"
            aria-label={`${nameIn(names, p.w.address)}: ${p.w.side} ${fmtUsd(p.w.size_usd)} from ${fmtLadderPx(p.w.entry)}. Open profile`}
            onPointerDown={e => { ptr.current = e.pointerType; }}
            onPointerEnter={e => { if (e.pointerType === "mouse" && !tip?.pinned) setTip({ i, via: "mouse" }); }}
            onPointerLeave={e => { if (e.pointerType === "mouse" && !tip?.pinned) setTip(null); }}
            onFocus={() => { if (!tip?.pinned) setTip({ i, via: ptr.current === "mouse" ? "mouse" : ptr.current ? "touch" : "key" }); }}
            onBlur={() => { if (!tip?.pinned) setTip(null); }}
            onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openProfile(p.w.address, e); } }}
            onClick={e => {
              e.stopPropagation();
              const how = ptr.current; ptr.current = null;
              // A mouse click opens the profile; a tap shows the wallet first, a second tap opens it.
              if (how === "mouse" || !how || (tip?.pinned && tip.i === i)) openProfile(p.w.address, e);
              else setTip({ i, pinned: true, via: "touch" });
            }} />)}
          {g.left.map((l, k) => <text key={`l${k}`} className="rl-line" x={l.x} y={l.y} textAnchor={l.anchor} style={{ fill: l.col }}>{l.t}</text>)}
          {g.right.map((l, k) => <text key={`r${k}`} className="rl-line" x={W - g.R - 4} y={l.y} textAnchor="end" style={{ fill: l.col }}>{l.t}</text>)}
          {!g.ws.length && <text className="rl-axl" x={g.mid} y={g.T + 40} textAnchor="middle">No profitable trader holds {c.coin}</text>}
        </svg>}
      {d && tipBox && <div className={`rl-tip${tip.pinned ? " pinned" : ""}`} style={tipBox} role="status">
        <div className="row"><b><WalletTag address={d.w.address} name={nameIn(names, d.w.address)} size={20} /></b><span style={{ color: d.col, fontWeight: 600 }}>{d.w.side === "long" ? "Long" : "Short"}</span></div>
        <div className="rl-tip-addr m">{shortAddr(d.w.address)}</div>
        <div className="row"><span>Size</span><span className="m">{fmtUsd(d.w.size_usd)}{d.w.leverage ? ` · ${Math.round(d.w.leverage)}x` : ""}</span></div>
        <div className="row"><span>Entry</span><span className="m">{fmtLadderPx(d.w.entry)}</span></div>
        <div className="row"><span>Unrealised</span><span className="m" style={{ color: (d.w.upnl || 0) >= 0 ? "var(--rd-long)" : "var(--rd-short)" }}>{pctText((d.w.move || 0) / 100)} · {(d.w.upnl || 0) >= 0 ? "+" : ""}{fmtUsd(d.w.upnl || 0)}</span></div>
        {d.w.roe != null && <div className="row"><span>On margin</span><span className="m">{pctText(d.w.roe / 100, 0)}</span></div>}
        {tip.pinned
          ? <Link className="rl-tip-go" to={traderPath(d.w.address)}>Open profile →</Link>
          : <div className="rl-tip-go">{tip.via === "key" ? "Press Enter to open profile" : "Click to open profile"}</div>}
      </div>}
    </div>
  </section>;
}

function LadderHelp({ tf }) {
  return <HelpTip title="Who is where" width={340}>
    <p>Each dot is one profitable trader at its entry price: longs left, shorts right. Dot area is the position in dollars, scaled to the largest wallet in this coin. Hover or tap a dot for the wallet; click it (or tap it again) to open the trader's profile.</p>
    <p>Solid line: price. Shaded: the coin's weekly support band (between its 20-week average and 21-week exponential average of Sunday closes). Dashed grey: trend, the {trendNote(null, tf).replace(/\.$/, "")}. Dashed green: the average long entry, weighted by dollars. Dotted: the median entry on each side.</p>
    <p>In their entry zone: price is within 3% of that average, with 3 or more profitable traders long.</p>
    <p>Wallets: Hyperliquid profitable traders, as on the Traders page.</p>
  </HelpTip>;
}

// The largest wallets in the followed coin, one row each (avatar and codename, side and size,
// entry, P&L), each a link to the trader's profile: the ladder's dots without aiming at them.
export function LadderWallets({ c, tf, n = 5 }) {
  const { data: lad } = useLadder(c?.coin, tf);
  const ws = lad?.positions || [];
  const top = useMemo(() => topWallets(ws, n), [ws, n]);
  const names = useMemo(() => viewNames(ws.map(w => w.address)), [ws]);
  if (!c || !top.length) return null;
  return <section className="rl-wallets" aria-labelledby={`rlw-${c.coin}`}>
    <div className="rl-w-head">
      <h3 id={`rlw-${c.coin}`}>Largest wallets in {c.coin}</h3>
      {ws.length > top.length && <span>{top.length} of {ws.length}</span>}
    </div>
    <ul className="rl-w-list">
      <li className="rl-w-cols" aria-hidden="true"><span /><span>Wallet</span><span>Entry</span><span>P&amp;L</span></li>
      {top.map(w => {
        const name = nameIn(names, w.address);
        const r = walletPnl(w);
        const side = w.side === "long" ? "Long" : "Short";
        return <li key={`${w.address}${w.side}`}>
          <Link className="rl-w-row" to={traderPath(w.address)} title={`${name}\n${w.address}`}
            aria-label={`${name}: ${side} ${fmtUsd(w.size_usd)}, entry ${fmtLadderPx(w.entry)}${r != null ? `, P&L ${pctText(r, 0)}` : ""}. Open profile`}>
            <WalletAvatar address={w.address} size={32} />
            <span className="rl-w-who">
              <span className="rl-w-name">{name}</span>
              <span className="rl-w-sub"><span style={{ color: w.side === "long" ? "var(--rd-long)" : "var(--rd-short)" }}>{side}</span> {fmtUsd(w.size_usd)}{w.leverage ? ` · ${Math.round(w.leverage)}x` : ""}</span>
            </span>
            <span className="rl-w-entry">{fmtLadderPx(w.entry)}</span>
            <span className="rl-w-pnl">
              {r != null && <b style={{ color: r >= 0 ? "var(--t-profit)" : "var(--t-loss)" }}>{pctText(r, 0)}</b>}
              {w.upnl != null && <small>{w.upnl >= 0 ? "+" : ""}{fmtUsd(w.upnl)}</small>}
            </span>
          </Link>
        </li>;
      })}
    </ul>
  </section>;
}
