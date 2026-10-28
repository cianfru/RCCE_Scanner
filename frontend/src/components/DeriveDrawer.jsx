import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Tabs from "./Tabs.jsx";
import { useWidth } from "./MarketHistoryChart.jsx";
import { Info } from "./MarketHistorySections.jsx";
import { T as TH } from "../theme.js";
import { apiFetch } from "../edge.js";
import { compactUsd, dayDate, logTicks, monthOf, usd } from "../utils/marketHistory.js";
import { COINS, DCOPY, RANGES, deriveRows, inRange, money, putScale, topsIn, weekly } from "../utils/deriveWallets.js";

// The market history page's Derive drawer: Derive's Smart options wallets against the price, as ranked at the time
// and as ranked today (the hindsight the owner's reading has to get past), and their new puts per week.

let cached = null;                                    // one fetch per page load; the seed changes by hand
const loadDerive = () => (cached ||= apiFetch("/api/market-history/derive").then(r => (r.ok ? r.json() : null)).catch(() => null));

const pts = list => list.map(([a, b]) => `${a.toFixed(1)},${b.toFixed(1)}`).join("L");

// Year (or month at 1Y) ticks along the bottom.
function ticks(d0, d1, short) {
  const out = [];
  const s = new Date(d0 * 86_400_000);
  for (let y = s.getUTCFullYear(), m = s.getUTCMonth() + 1; ; m++) {
    if (m > 11) { m = 0; y++; }
    const day = Date.UTC(y, m, 1) / 86_400_000;
    if (day > d1) break;
    if (short ? m % 3 === 0 : m === 0) out.push({ day, label: m === 0 ? String(y) : monthOf(day) });
  }
  return out;
}

function Chart({ rows, coin, tops, smartToday }) {
  const [box, W] = useWidth(900);
  const [hov, setHov] = useState(null);
  if (rows.length < 2) return <div ref={box} className="mh-empty">{DCOPY.unavailable}</div>;
  const phone = W < 520;
  const padL = 8, padR = 48, gap = 14, labelH = 18;
  const hP = phone ? 96 : 130, hC = phone ? 84 : 110, hW = phone ? 64 : 84;
  // Panel tops: price, ranked at the time, ranked today, new puts; each with a label row above it.
  const y0 = [labelH];
  y0.push(y0[0] + hP + gap + labelH);
  y0.push(y0[1] + hC + gap + labelH);
  y0.push(y0[2] + hC + gap + labelH);
  const bottom = y0[3] + hW, H = bottom + 18;
  const d0 = rows[0].day, d1 = rows[rows.length - 1].day;
  const x = d => padL + ((d - d0) / Math.max(1, d1 - d0)) * (W - padL - padR);
  // Price, log scale.
  const ps = rows.map(r => r.price).filter(v => v > 0);
  const lo = Math.min(...ps), hi = Math.max(...ps);
  const yP = v => y0[0] + 3 + (1 - (Math.log(v) - Math.log(lo)) / (Math.log(hi) - Math.log(lo) || 1)) * (hP - 6);
  // Counts: one scale for both panels, so the two rankings compare.
  const cmax = Math.max(4, ...rows.flatMap(r => [r.pitL, r.pitS, r.nowL, r.nowS])) * 1.08;
  const yC = (top, v) => top + hC / 2 - (v / cmax) * (hC / 2 - 2);
  const weeks = weekly(rows, "pitPuts");
  const pm = putScale(weeks);
  const yW = v => y0[3] + hW - (Math.min(v, pm) / pm) * (hW - 2);
  const bw = Math.max(1, (x(d0 + 7) - x(d0)) * 0.7);
  const green = TH.green, red = TH.red;
  const line = get => { let d = "", pen = false; for (const r of rows) { const v = get(r); if (v == null) { pen = false; continue; } d += `${pen ? "L" : "M"}${x(r.day).toFixed(1)},${v.toFixed(1)}`; pen = true; } return d; };
  const area = (top, get, sign) => `M${x(d0).toFixed(1)},${yC(top, 0).toFixed(1)}L${pts(rows.map(r => [x(r.day), yC(top, sign * get(r))]))}L${x(d1).toFixed(1)},${yC(top, 0).toFixed(1)}Z`;
  const counts = (top, L, S) => <g>
    <line className="mh-zero" x1={padL} x2={W - padR} y1={yC(top, 0)} y2={yC(top, 0)} />
    {[Math.round(cmax / 2), -Math.round(cmax / 2)].map(v => <g key={v}>
      <line className="mh-wallet-guide" x1={padL} x2={W - padR} y1={yC(top, v)} y2={yC(top, v)} />
      <text className="mh-tick" x={W - padR + 6} y={yC(top, v) + 4}>{Math.abs(v)}</text>
    </g>)}
    <text className="mh-tick" x={W - padR + 6} y={yC(top, 0) + 4}>0</text>
    <path className="mh-wallet-area" style={{ fill: green }} d={area(top, r => r[L], 1)} />
    <path className="mh-wallet-area" style={{ fill: red }} d={area(top, r => r[S], -1)} />
    <path className="mh-wallet-line" style={{ stroke: green }} d={line(r => yC(top, r[L]))} />
    <path className="mh-wallet-line" style={{ stroke: red }} d={line(r => yC(top, -r[S]))} />
  </g>;
  const onMove = e => {
    const rect = e.currentTarget.getBoundingClientRect();
    const day = d0 + ((((e.clientX - rect.left) / rect.width) * W - padL) / (W - padL - padR)) * (d1 - d0);
    let best = 0;
    for (let i = 0; i < rows.length; i++) if (Math.abs(rows[i].day - day) < Math.abs(rows[best].day - day)) best = i;
    setHov(best);
  };
  const h = rows[hov ?? rows.length - 1];
  const wk = weeks.find(w => h.day >= w.day && h.day < w.day + 7);
  const label = (i, text, pop) => <span className="mh-btc-label dd-label" style={{ left: padL + 2, top: y0[i] - labelH + 1 }}>{text}{pop}</span>;
  return <div ref={box} className="mh-chart dd-chart">
    <div className="mh-chart-plot">
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" onPointerMove={onMove} onPointerDown={onMove}
        onPointerLeave={e => { if (e.pointerType === "mouse") setHov(null); }}
        aria-label={`${DCOPY.panel.price(coin)}, ${DCOPY.panel.pit}, ${DCOPY.panel.now}, ${DCOPY.panel.puts}`}>
        {logTicks(lo, hi).map(v => <g key={v}>
          <line className="mh-grid" x1={padL} x2={W - padR} y1={yP(v)} y2={yP(v)} />
          <text className="mh-tick" x={W - padR + 6} y={yP(v) + 4}>{compactUsd(v)}</text>
        </g>)}
        <path className="mh-btc" d={line(r => (r.price ? yP(r.price) : null))} />
        {counts(y0[1], "pitL", "pitS")}
        {counts(y0[2], "nowL", "nowS")}
        {weeks.map(w => <g key={w.day}>
          <rect className="dd-put" x={x(w.day)} width={bw} y={yW(w.sum)} height={Math.max(0, y0[3] + hW - yW(w.sum))} />
          {w.sum > pm && <line className="mh-notch" x1={x(w.day) - 1} x2={x(w.day) + bw + 1} y1={yW(pm * 0.86)} y2={yW(pm * 0.86)} />}
        </g>)}
        <line className="mh-zero" x1={padL} x2={W - padR} y1={y0[3] + hW} y2={y0[3] + hW} />
        <text className="mh-tick" x={W - padR + 6} y={y0[3] + 10}>{money(pm / 1.08)}</text>
        {tops.map(d => <line key={d} className="dd-top" x1={x(d)} x2={x(d)} y1={y0[0]} y2={bottom} />)}
        {ticks(d0, d1, d1 - d0 < 400).map(t => <text key={t.day} className="mh-tick" x={x(t.day)} y={H - 4} textAnchor="middle">{t.label}</text>)}
        {hov != null && <line className="mh-cursor" x1={x(h.day)} x2={x(h.day)} y1={0} y2={bottom} />}
      </svg>
      {label(0, DCOPY.panel.price(coin), <Info title={DCOPY.pop.priceTitle} paras={DCOPY.pop.price()} />)}
      {label(1, <>{DCOPY.panel.pit}<span className="mh-wallet-key" aria-hidden="true"><i className="is-long" />{DCOPY.long}<i className="is-short" />{DCOPY.short}</span></>,
        <Info title={DCOPY.pop.pitTitle} paras={DCOPY.pop.pit()} />)}
      {label(2, DCOPY.panel.now, <Info title={DCOPY.pop.nowTitle} paras={DCOPY.pop.now(smartToday)} />)}
      {label(3, DCOPY.panel.puts, <Info title={DCOPY.pop.putsTitle} paras={DCOPY.pop.puts()} />)}
    </div>
    <table className="mh-readout dd-readout">
      <thead><tr><th scope="col" /><th scope="col">{dayDate(h.day)}</th></tr></thead>
      <tbody>
        <tr><th scope="row">{DCOPY.readout.price(coin)}</th><td><b>{usd(h.price)}</b></td></tr>
        <tr><th scope="row">{DCOPY.readout.pit}</th><td><b>{DCOPY.readout.counts(h.pitL, h.pitS)}</b></td></tr>
        <tr><th scope="row">{DCOPY.readout.now}</th><td><b>{DCOPY.readout.counts(h.nowL, h.nowS)}</b></td></tr>
        <tr><th scope="row">{DCOPY.readout.puts}</th><td><b>{money(wk?.sum)}</b></td></tr>
      </tbody>
    </table>
  </div>;
}

export default function DeriveDrawer({ onClose }) {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  const [coin, setCoin] = useState("BTC");
  const [range, setRange] = useState("all");
  const closeRef = useRef(null);
  const opener = useRef(typeof document !== "undefined" ? document.activeElement : null);
  useEffect(() => {
    let alive = true;
    loadDerive().then(d => { if (!alive) return; if (d?.rows?.length) setData(d); else setFailed(true); });
    return () => { alive = false; };
  }, []);
  useEffect(() => {
    closeRef.current?.focus();
    const prev = opener.current;
    // Escape closes an open info popover first (HelpTip handles it), the drawer otherwise.
    const onKey = e => { if (e.key === "Escape" && !document.querySelector(".alt-season-explanation")) onClose(); };
    document.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = overflow; prev?.focus?.(); };
  }, [onClose]);
  const rows = useMemo(() => inRange(deriveRows(data, coin), range), [data, coin, range]);
  const tops = rows.length ? topsIn(data, coin, rows[0].day, rows[rows.length - 1].day) : [];
  return createPortal(<div className="reflex-terminal">
    <div className="mh-backdrop" onClick={onClose} />
    <aside className="mh-drawer dd-drawer" role="dialog" aria-modal="true" aria-labelledby="dd-title">
      <header className="mh-head">
        <h2 id="dd-title">{DCOPY.title}<Info title={DCOPY.pop.aboutTitle} paras={DCOPY.pop.about()} /></h2>
        <button ref={closeRef} type="button" className="mh-close" onClick={onClose}>{DCOPY.close}</button>
      </header>
      <div className="mh-body">
        {!data ? <p className="mh-muted">{failed ? DCOPY.unavailable : DCOPY.loading}</p> : <>
          <p className="mh-sub">{DCOPY.sub(data.through, data.smart_today)}</p>
          <div className="mh-controls">
            <Tabs small label={DCOPY.coinLabel} items={COINS} value={coin} onChange={setCoin} />
            <Tabs small label={DCOPY.rangeLabel} items={RANGES} value={range} onChange={setRange} />
          </div>
          <Chart rows={rows} coin={coin} tops={tops} smartToday={data.smart_today} />
        </>}
      </div>
    </aside>
  </div>, document.body);
}
