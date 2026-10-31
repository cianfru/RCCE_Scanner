import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import Tabs from "./Tabs.jsx";
import HelpTip from "./HelpTip.jsx";
import { apiJson } from "../edge.js";
import { getBaseSymbol } from "../theme.js";
import { sideBarColor } from "../utils/traderFormat.js";
import { dayLabel, timeTicks, usd } from "../utils/cohorts.js";
import { points, runs, peak, nearest, everHeld, recorded, niceMax, count, tickLabel } from "../utils/coinPositioning.js";
import { COIN_GROUPS, groupDefinitions } from "../utils/traderGroups.js";
import useRosterCounts from "../hooks/useRosterCounts.js";
import { pollWhileVisible } from "../utils/visiblePoll.js";

const MEASURES = [{ key: "n", label: "Traders", title: "Wallets on each side" }, { key: "usd", label: "$", title: "Position value on each side" }];
const RANGES = [{ key: "7", label: "7D" }, { key: "30", label: "30D" }, { key: "90", label: "90D" }];

const when = ts => {
  const d = new Date(ts * 1000);
  return `${dayLabel(ts)} ${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")} UTC`;
};

// One group: long above the line, short below it, on one scale.
function Panel({ group, pts, t0, t1, width, hover, onHover, rebuilds, measure }) {
  const phone = width < 420;
  const plotH = phone ? 96 : 116;
  const padL = 40, padR = 8, padT = 4, padB = 18, H = plotH + padT + padB;
  const plotW = Math.max(1, width - padL - padR);
  const top = niceMax(peak(pts));
  const mid = padT + plotH / 2;
  const x = t => padL + ((t - t0) / (t1 - t0 || 1)) * plotW;
  const yl = v => mid - (v / top) * (plotH / 2);
  const ys = v => mid + (v / top) * (plotH / 2);
  const area = (run, side) => {
    const y = side === "long" ? yl : ys;
    if (run.length === 1) {
      const cx = x(run[0].t);
      return `M${(cx - 1.5).toFixed(1)},${mid}V${y(run[0][side]).toFixed(1)}H${(cx + 1.5).toFixed(1)}V${mid}Z`;
    }
    return `M${x(run[0].t).toFixed(1)},${mid}` + run.map(p => `L${x(p.t).toFixed(1)},${y(p[side]).toFixed(1)}`).join("")
      + `L${x(run[run.length - 1].t).toFixed(1)},${mid}Z`;
  };
  const edge = (run, side) => run.map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(1)},${(side === "long" ? yl : ys)(p[side]).toFixed(1)}`).join("");
  const at = hover ?? t1;
  const p = nearest(pts, at);
  const fmt = measure === "usd" ? usd : count;
  const held = everHeld(pts);
  const first = pts.find(q => q.long != null)?.t;
  const ticks = timeTicks(t0, t1, Math.max(2, Math.floor(plotW / (phone ? 80 : 110)))).filter(t => x(t.ts) > padL + 14 && x(t.ts) < width - padR - 14);
  const onMove = e => {
    const r = e.currentTarget.getBoundingClientRect();
    onHover(Math.min(t1, Math.max(t0, t0 + ((e.clientX - r.left - padL) / plotW) * (t1 - t0))));
  };
  const lc = sideBarColor("long"), sc = sideBarColor("short");
  return <div className="cpos-panel" role="group" aria-label={group.name}>
    <div className="cpos-ph">
      <span className="cpos-name">{group.name}</span>
      <span className="cpos-sub">{group.sub}</span>
      <span className="cpos-val">{p ? <>
        <b style={{ color: lc }}>{fmt(p.long)}</b> long<span className="cpos-dot">·</span><b style={{ color: sc }}>{fmt(p.short)}</b> short
      </> : "—"}</span>
    </div>
    {!held ? <p className="cpos-empty" style={{ height: H }}>{!recorded(pts) ? "Not recorded yet."
      : first - t0 > 2 * 86400 ? `None held it since ${dayLabel(first)}, when its record starts.` : "None held it in this period."}</p> : (
      <svg viewBox={`0 0 ${width} ${H}`} width={width} height={H} role="img"
        aria-label={`${group.name}: ${measure === "usd" ? "value" : "wallets"} long above the line, short below, over time`}
        onPointerMove={onMove} onPointerDown={onMove} onPointerLeave={e => { if (e.pointerType === "mouse") onHover(null); }}>
        {ticks.map(t => <line key={t.ts} className="cpos-vgrid" x1={x(t.ts)} x2={x(t.ts)} y1={padT} y2={padT + plotH} />)}
        {rebuilds.map(r => <line key={r.t} className="cpos-rebuild" x1={x(r.t)} x2={x(r.t)} y1={padT} y2={padT + plotH}>
          <title>{r.note === "rules" ? `List rules changed ${when(r.t)}` : `List rebuilt ${when(r.t)}: ${r.joined} joined${r.left != null ? `, ${r.left} left` : ""}`}</title></line>)}
        {runs(pts).map(run => <g key={run[0].t}>
          <path d={area(run, "long")} fill={lc} className="cpos-area" />
          <path d={area(run, "short")} fill={sc} className="cpos-area" />
          {run.length > 1 && <path d={edge(run, "long")} stroke={lc} className="cpos-edge" />}
          {run.length > 1 && <path d={edge(run, "short")} stroke={sc} className="cpos-edge" />}
        </g>)}
        <line className="cpos-zero" x1={padL} x2={width - padR} y1={mid} y2={mid} />
        <text className="cpos-tick" x={padL - 6} y={padT + 9} textAnchor="end">{tickLabel(top, measure)}</text>
        <text className="cpos-tick" x={padL - 6} y={padT + plotH} textAnchor="end">{tickLabel(top, measure)}</text>
        {ticks.map(t => <text key={t.ts} className="cpos-tick" x={x(t.ts)} y={H - 4} textAnchor="middle">{t.label}</text>)}
        {first != null && first - t0 > 2 * 86400 && <text className="cpos-since" x={padL + 6} y={mid - 6}>from {dayLabel(first)}</text>}
        {hover != null && <>
          <line className="cpos-cursor" x1={x(hover)} x2={x(hover)} y1={padT} y2={padT + plotH} />
          {p && <><circle className="cpos-mark" cx={x(p.t)} cy={yl(p.long)} r={3} fill={lc} />
            <circle className="cpos-mark" cx={x(p.t)} cy={ys(p.short)} r={3} fill={sc} /></>}
        </>}
      </svg>
    )}
  </div>;
}

// A coin's long and short over time for four groups of wallets (definitions behind the (i)).
export default function CoinPositioning({ symbol, spot = false }) {
  const coin = getBaseSymbol(symbol || "");
  const [measure, setMeasure] = useState("n");
  const [days, setDays] = useState("30");
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  const [hover, setHover] = useState(null);
  const [W, setW] = useState(0);
  const box = useRef(null);
  const counts = useRosterCounts();
  const defs = groupDefinitions(counts);
  // Builder-dex markets (xyz:) are in neither record: no card rather than empty panels.
  const hidden = coin.toLowerCase().startsWith("xyz:") || data?.covered === false;

  useLayoutEffect(() => {
    if (!box.current) return undefined;
    setW(Math.round(box.current.clientWidth));
    if (typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(([e]) => setW(Math.round(e.contentRect.width)));
    ro.observe(box.current);
    return () => ro.disconnect();
  }, [hidden]);

  useEffect(() => { setData(null); setHover(null); }, [coin]);
  useEffect(() => { setHover(null); }, [days]);      // a pinned (tapped) time can fall outside the new range
  useEffect(() => {
    if (!coin || coin.toLowerCase().startsWith("xyz:")) return undefined;
    let alive = true;
    setFailed(false);
    const load = () => apiJson(`/api/coin-positioning?coin=${encodeURIComponent(coin)}&days=${days}`)
      .then(d => { if (alive) { setData(d); setFailed(false); } })
      .catch(() => { if (alive) setFailed(true); });
    load();
    const stop = pollWhileVisible(load, 600_000);
    return () => { alive = false; stop(); };
  }, [coin, days]);

  const series = useMemo(() => COIN_GROUPS.map(g => ({ group: g, pts: points(data?.groups?.[g.key], measure) })), [data, measure]);
  const all = series.flatMap(s => s.pts.filter(p => p.long != null).map(p => p.t));
  const t0 = all.length ? Math.min(...all) : 0, t1 = all.length ? Math.max(...all) : 0;
  const cols = W >= 760 ? 2 : 1;
  const panelW = cols === 2 ? Math.floor((W - 28) / 2) : W;
  const latestLive = series.some(s => data?.groups?.[s.group.key]?.live);
  if (hidden) return null;

  return <section className="analysis-card cpos">
    <div className="cpos-head">
      <h3>Long and short on {coin}{spot ? " (Hyperliquid perps)" : ""} <HelpTip title="Who is counted" width={420}>
        <p>{defs.profitable}</p>
        <p>{defs.winners} {defs.losers} {defs.whales}</p>
        <p>{defs.windows} {defs.sweep}</p>
        <p>Above the line long {coin}, below it short; each wallet counts once. Readings every 4 hours{latestLive ? ", plus the latest" : ""}.</p>
        <p>Dotted lines: the profitable-trader list was rebuilt or its rules changed. A step there is the list changing, not trading.</p>
      </HelpTip></h3>
      <div className="cpos-ctl">
        <Tabs small label="Measure" items={MEASURES} value={measure} onChange={setMeasure} />
        <Tabs small label="Range" items={RANGES} value={days} onChange={setDays} />
      </div>
    </div>
    <div className="cpos-at" aria-live="off">{t1 ? (hover == null ? `Latest · ${when(t1)}` : when(hover)) : " "}</div>
    <div ref={box} className="cpos-grid" data-cols={cols}>
      {!data || (failed && String(data.days) !== days) ? <p className="cpos-empty">{failed ? "Could not load the readings." : "Loading…"}</p>
        : !all.length ? <p className="cpos-empty">No readings for {coin} yet.</p>
        : W > 0 && series.map(({ group, pts }) => <Panel key={group.key} group={group} pts={pts} t0={t0} t1={t1} width={panelW}
          hover={hover} onHover={setHover} measure={measure} rebuilds={group.key === "profitable" ? (data.rebuilds || []).filter(r => r.t >= t0 && r.t <= t1) : []} />)}
    </div>
  </section>;
}
