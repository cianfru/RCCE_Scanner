// "Three layers. One read.": a scroll-driven drawing of how the Radar is built.
// Each coin sits on a line by the engine's stretch (z-score), coloured by its regime; it rises by
// the profitable traders net long; the line folds into the Radar (bubbles, the Early setups box,
// the weekly-band rings); one coin lifts out into a read row. Reduced motion: the finished still.
import { useEffect, useMemo, useRef, useState } from "react";
import { REGIME_META } from "../theme.js";
import { stageColor } from "../components/radar/shared.jsx";
import { visible, symlog } from "../utils/setupMap.js";
import { bandInfo } from "../utils/radarDepth.js";
import TokenLogo from "../components/TokenLogo.jsx";

const XS = [-2.5, 3.5];
const clamp = v => Math.max(0, Math.min(1, v));
const ease = t => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const mix = (a, b, t) => a + (b - a) * t;
const STEPS = [
  { k: "Engine", t: "Each coin by stretch", d: "Across: the engine's z-score. Colour: its regime." },
  { k: "Traders", t: "Lifted by who is long", d: "Up: profitable traders net long." },
  { k: "Radar", t: "Folded into one map", d: "Size: dollars they hold. Box: early setups. Ring: the weekly band." },
  { k: "Read", t: "One coin, one line", d: "Everything the three layers say about it." },
];
const TONE = { halo: "var(--rd-halo)", violet: "var(--rd-inband)", red: "var(--rd-red)" };
const pct = v => (v == null ? "—" : `${v > 0 ? "+" : ""}${Number(v).toFixed(1)}%`);
const EMPTY = { coins: [], box: { z: [-0.5, 1.5], n: [1, 8] } };

// Coin labels that never cross: the followed coin first, then by bubble size; each tries the
// right, left, above and below of its bubble and is left out when all four are taken.
function placeLabels(items, bubbles) {
  const placed = [];
  const hit = (b, o) => b.x < o.x + o.w && o.x < b.x + b.w && b.y < o.y + o.h && o.y < b.y + b.h;
  const out = [];
  for (const it of items) {
    const w = 7.4 * it.coin.length + 4, h = 14;
    const tries = [
      { x: it.x + it.r + 4, y: it.y - h / 2, anchor: "start", tx: it.x + it.r + 6, ty: it.y + 4 },
      { x: it.x - it.r - 4 - w, y: it.y - h / 2, anchor: "end", tx: it.x - it.r - 6, ty: it.y + 4 },
      { x: it.x - w / 2, y: it.y - it.r - 4 - h, anchor: "middle", tx: it.x, ty: it.y - it.r - 7 },
      { x: it.x - w / 2, y: it.y + it.r + 4, anchor: "middle", tx: it.x, ty: it.y + it.r + 15 },
    ];
    const ok = tries.find(t => {
      const b = { x: t.x, y: t.y, w, h };
      return !placed.some(o => hit(b, o)) && !bubbles.some(o => o.coin !== it.coin && hit(b, { x: o.x - o.r, y: o.y - o.r, w: 2 * o.r, h: 2 * o.r }));
    });
    if (!ok) continue;
    placed.push({ x: ok.x, y: ok.y, w, h });
    out.push({ ...it, ...ok });
  }
  return out;
}

export default function FoldDiagram({ data, focus, reduced, phone }) {
  const smap = data || EMPTY;
  // A taller drawing on phones, so the coins and labels stay legible.
  const [VW, VH, L, R, T, B, RMAX] = phone ? [420, 560, 40, 12, 30, 52, 28] : [1000, 560, 56, 24, 36, 56, 46];
  const host = useRef(null);
  const [p, setP] = useState(reduced ? 1 : 0);
  useEffect(() => {
    if (reduced) return undefined;
    let frame = 0;
    const read = () => {
      frame = 0;
      const el = host.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const span = r.height - window.innerHeight;
      setP(clamp(-r.top / Math.max(1, span)));
    };
    const on = () => { if (!frame) frame = requestAnimationFrame(read); };
    read();
    window.addEventListener("scroll", on, { passive: true });
    window.addEventListener("resize", on);
    return () => { cancelAnimationFrame(frame); window.removeEventListener("scroll", on); window.removeEventListener("resize", on); };
  }, [reduced]);

  const coins = useMemo(() => visible(smap.coins, { side: "long" }).filter(c => c.zscore != null), [smap]);
  const box = smap.box;
  const nets = coins.map(c => (c.traders?.pl || 0) - (c.traders?.ps || 0));
  const ys = [symlog(Math.min(-4, ...nets)), symlog(Math.max(25, ...nets)) + 0.06];
  const X = z => L + ((Math.max(XS[0], Math.min(XS[1], z)) - XS[0]) / (XS[1] - XS[0])) * (VW - L - R);
  const Y = n => T + (1 - (symlog(n) - ys[0]) / (ys[1] - ys[0])) * (VH - T - B);
  const G = Math.max(0, ...coins.map(c => c.money?.gross_usd || 0));
  const lineY = (VH - B + T) / 2;

  // Phases: line, rise, fold, read.
  const a = ease(clamp((p - 0.12) / 0.26));     // rise
  const f = ease(clamp((p - 0.42) / 0.26));     // fold
  const r = ease(clamp((p - 0.74) / 0.2));      // read
  const step = p < 0.12 ? 0 : p < 0.42 ? 1 : p < 0.74 ? 2 : 3;
  const fc = focus;
  const focusCoin = fc?.coin;
  const geo = coins.map(c => {
    const n = (c.traders?.pl || 0) - (c.traders?.ps || 0);
    const rb = c.money?.gross_usd > 0 && G ? Math.max(phone ? 2.4 : 3.2, RMAX * Math.sqrt(c.money.gross_usd / G)) : 2.2;
    return { c, coin: c.coin, x: X(c.zscore), y: mix(lineY, Y(n), a), rb, r: mix(phone ? 3 : 4, rb, f) };
  });
  // Labels: on the line only the followed coin (above it); once folded, the biggest bubbles too.
  const big = phone ? 12 : 16;
  const labelled = a < 0.5
    ? (fc ? [{ ...geo.find(g => g.coin === focusCoin), above: true }].filter(g => g.coin) : [])
    : placeLabels([...geo.filter(g => g.coin === focusCoin), ...geo.filter(g => g.coin !== focusCoin && f > 0.6 && g.rb >= big).sort((u, v) => v.rb - u.rb)],
      geo.filter(g => g.r >= 6));

  return <section className={`lp-fold${reduced ? " still" : ""}`} ref={host} aria-labelledby="lp-fold-h">
    <div className="lp-fold-stick">
      <div className="lp-width lp-fold-grid">
        <div className="lp-fold-copy">
          <h2 id="lp-fold-h">Three layers. <span>One read.</span></h2>
          <ol className="lp-steps">
            {STEPS.map((s, i) => <li key={s.k} className={reduced || i === step ? "on" : i < step ? "done" : ""}>
              <span className="lp-step-k">{String(i + 1).padStart(2, "0")} · {s.k}</span>
              <b>{s.t}</b>
              <span className="lp-step-d">{s.d}</span>
            </li>)}
          </ol>
        </div>
        <div className="lp-fold-art">
          <svg viewBox={`0 0 ${VW} ${VH}`} role="img" aria-label="Coins placed by stretch, lifted by profitable traders net long, folded into the Radar map">
            {/* Early setups box and the stretched zone arrive with the fold. */}
            <g opacity={f}>
              <rect x={X(box.z[1] + 0.5)} y={T} width={VW - R - X(box.z[1] + 0.5)} height={VH - B - T} className="lp-fold-late" />
              <rect x={X(box.z[0])} y={Y(box.n[1])} width={X(box.z[1]) - X(box.z[0])} height={Y(box.n[0]) - Y(box.n[1])} className="lp-fold-box" />
              <text className="lp-fold-zone" x={X(box.z[0]) + 8} y={Y(box.n[1]) + 18}>Early setups</text>
              {[-3, 0, 1, 3, 8, 20, 50].map(t => <g key={t}><line className="lp-fold-ax" x1={L} x2={VW - R} y1={Y(t)} y2={Y(t)} /><text className="lp-fold-axt" x={L - 8} y={Y(t) + 4} textAnchor="end">{t > 0 ? "+" : ""}{t}</text></g>)}
            </g>
            {/* The engine's axis: always there. */}
            <line className="lp-fold-axis" x1={L} x2={VW - R} y1={mix(lineY, Y(0), a)} y2={mix(lineY, Y(0), a)} />
            {[-2, -1, 0, 1, 2, 3].map(t => <text key={t} className="lp-fold-axt" x={X(t)} y={VH - B + 22} textAnchor="middle">{t > 0 ? "+" : ""}{t}</text>)}
            <text className="lp-fold-axl" x={L} y={VH - 12}>Near its mean</text>
            <text className="lp-fold-axl" x={VW - R} y={VH - 12} textAnchor="end">Stretched</text>
            <text className="lp-fold-axl" transform={`translate(14,${T + 4}) rotate(-90)`} textAnchor="end" opacity={a}>More profitable traders long</text>
            {geo.map(({ c, x, y, rb, r: rad }) => {
              const regime = (REGIME_META[c.regime] || REGIME_META.FLAT).color;
              const on = c.coin === focusCoin;
              const dim = on ? 1 : mix(1, 0.28, r);
              const bi = bandInfo(c.band, c.price);
              const ring = f > 0 && rb >= 7 && bi.tone !== "none" && bi.fill > 0;
              return <g key={c.coin} transform={`translate(${x.toFixed(1)},${y.toFixed(1)})`} opacity={dim}>
                {ring && <circle r={rad + 3.5} fill="none" stroke={TONE[bi.tone]} strokeOpacity={f} strokeWidth="1.8"
                  strokeDasharray={`${(2 * Math.PI * (rad + 3.5) * bi.fill).toFixed(1)} 999`} transform="rotate(-90)" />}
                {f < 1 && <circle r={rad} fill={regime} fillOpacity={0.9 * (1 - f)} />}
                {f > 0 && <circle r={rad} fill={stageColor(c.stage)} fillOpacity={(rb >= 12 ? 0.58 : 0.9) * f} />}
                {on && <circle r={rad + 7} fill="none" stroke="#F5FEFD" strokeWidth="1.5" opacity={Math.max(a * 0.2, r)} />}
              </g>;
            })}
            {labelled.map(l => l.above
              ? <text key={l.coin} className="lp-fold-lab" x={l.x} y={l.y - l.r - 8} textAnchor="middle">{l.coin}</text>
              : <text key={l.coin} className="lp-fold-lab" x={l.tx} y={l.ty} textAnchor={l.anchor} opacity={l.coin === focusCoin ? 1 : mix(0.35, 1, 1 - r) * f}>{l.coin}</text>)}
          </svg>
          {fc && <div className="lp-read" style={{ opacity: r, transform: `translateY(${(1 - r) * 24}px)` }} aria-hidden={r < 0.5}>
            <span className="lp-read-coin"><TokenLogo symbol={fc.symbol} size={22} />{fc.coin}</span>
            <span><small>Regime</small><b className="w"><i style={{ background: REGIME_META[fc.regime]?.color }} />{REGIME_META[fc.regime]?.name}</b></span>
            <span><small>Checks</small><b>{fc.checks ? `${fc.checks[0]}/${fc.checks[1]}` : "—"}</b></span>
            <span><small>Profitable traders long</small><b>{fc.traders?.pl ?? "—"}</b></span>
            <span><small>From their entry</small><b>{pct(fc.entry?.dist_pct)}</b></span>
            <span><small>Weekly band</small><b>{bandInfo(fc.band, fc.price).short}</b></span>
          </div>}
        </div>
      </div>
    </div>
  </section>;
}
