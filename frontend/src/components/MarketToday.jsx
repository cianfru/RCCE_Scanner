import { useMemo, useState } from "react";
import { Info } from "./MarketHistorySections.jsx";
import { CYCOPY, marketCycles, readingAgo, shareBelow } from "../utils/marketCycles.js";
import { dayDate, monthYear } from "../utils/marketHistory.js";
import { byDay } from "../utils/walletHistory.js";

// The market page's top row, above its tabs: where the market stands today in four tiles, each a number and a small
// picture of it; the number opens its tab. Coins in uptrend against the 55% line, with yesterday and a week ago marked;
// the broad downturn's (or uptrend's) day against how long past ones lasted (point at a dot for that one); Fear & Greed
// on its 0-100 scale; profitable traders' long and short split, with yesterday's and last week's long share marked.

const pct = v => `${Math.round(100 * v)}%`;

// Yesterday's and last week's readings as thin marks on a bar, each named under it (0-100 scale).
function Ago({ marks }) {
  const shown = marks.filter(m => m.v != null);
  if (!shown.length) return null;
  // Two marks closer than 7% of the bar: the week's label goes on the other side so the two never touch.
  const near = shown.length === 2 && Math.abs(shown[0].v - shown[1].v) < 7;
  return <>
    {shown.map((m, i) => {
      const at = Math.max(0, Math.min(100, m.v));
      const side = near && i === 1 ? (shown[1].v < shown[0].v ? "is-left" : "is-right") : "";
      return <span key={m.key} className="mt-ago" style={{ left: `${at}%` }} title={m.title}>
        <span className={`mt-ago-label ${side}`}>{m.key}</span>
      </span>;
    })}
  </>;
}

function Bar({ v, marks = [], ago = [], tone = "accent", label }) {
  const at = Math.max(0, Math.min(100, v));
  return <span className={`mt-bar is-${tone}${ago.some(m => m.v != null) ? " has-ago" : ""}`} role="img" aria-label={label}>
    <span className="mt-bar-fill" style={{ width: `${at}%` }} />
    {marks.map(m => <span key={m} className="mt-bar-mark" style={{ left: `${m}%` }} />)}
    <Ago marks={ago} />
  </span>;
}

// Each past one's length as a dot on one line, today's day as a short bar on it. Pointing along the line names the
// nearest past one in a small box and lights its line in the Cycles chart below (onHover: { kind, start } or null).
function Lengths({ c, onHover }) {
  const [hov, setHov] = useState(null);
  const [box, setBox] = useState(null);             // the strip's left and width, and the window's width, in px
  const max = Math.max(c.today.days, ...c.past.map(p => p.days));
  const x = d => Math.min(100, (100 * d) / max);
  const onMove = e => {
    const r = e.currentTarget.getBoundingClientRect();
    const f = ((e.clientX - r.left) / r.width) * max;
    let best = 0;
    c.past.forEach((p, i) => { if (Math.abs(p.days - f) < Math.abs(c.past[best].days - f)) best = i; });
    setHov(best);
    setBox({ left: r.left, width: r.width, view: window.innerWidth });
    onHover?.({ kind: c.kind, start: c.past[best].start });
  };
  // The card's left edge in px from the strip's: centred on the dot, kept 8px inside the window.
  const POP_W = 220;
  const popLeft = d => {
    if (!box) return 0;
    const want = (x(d) / 100) * box.width - POP_W / 2;
    return Math.max(8 - box.left, Math.min(box.view - 8 - box.left - POP_W, want));
  };
  const p = hov != null ? c.past[hov] : null;
  return <span className="mt-lengths" onPointerMove={onMove} onPointerDown={onMove} onPointerLeave={() => { setHov(null); onHover?.(null); }}
    role="img" aria-label={`Past lengths ${c.past.map(q => q.days).sort((a, b) => a - b).join(", ")} days; today day ${c.today.days}`}>
    <span className="mt-lengths-axis" />
    {c.past.map((q, i) => <span key={q.start} className={hov === i ? "mt-lengths-dot is-hov" : "mt-lengths-dot"} style={{ left: `${x(q.days)}%` }} />)}
    <span className="mt-lengths-now" style={{ left: `${x(c.today.days)}%` }} />
    {p && <span className="mt-pop mh-hover-tip" role="status" style={{ left: popLeft(p.days), width: POP_W }}>
      <b>{monthYear(p.start)} · {p.days} days</b>
      <span>{dayDate(p.start)} – {dayDate(p.end - 1)}</span>
      {CYCOPY.tip(p, c.kind, dayDate).slice(2).map(l => <span key={l}>{l}</span>)}
    </span>}
  </span>;
}

function Tile({ label, info, tab, onPick, aria, children }) {
  return <div className="mt-tile">
    <span className="mt-label">{label}{info}</span>
    <button type="button" className="mt-body" onClick={() => onPick(tab)} aria-label={aria}>{children}</button>
  </div>;
}

export default function MarketToday({ data, rows, wallets, onPick, onHoverCycle }) {
  const c = useMemo(() => marketCycles(rows), [rows]);
  const last = rows[rows.length - 1];
  const share = data?.today?.uptrend ?? last?.uptrend;
  const below = useMemo(() => shareBelow(rows.map(r => r.uptrend), share), [rows, share]);
  const sharePts = useMemo(() => rows.map(r => ({ day: r.day, v: r.uptrend })), [rows]);
  // Fear & Greed: the index's newest reading, which can be a day newer than the market history.
  const fgAll = data?.fear_greed || [];
  const fg = fgAll.length ? { day: fgAll[fgAll.length - 1][0], v: fgAll[fgAll.length - 1][1] } : null;
  const crowdPts = useMemo(() => [...(byDay(wallets, { scope: "all" }).crowd?.values() || [])]
    .map(r => ({ day: r.day, v: r.L, S: r.S })).sort((a, b) => a.day - b.day), [wallets]);
  const crowd = crowdPts.length ? crowdPts[crowdPts.length - 1] : null;
  const ago = (pts, scale) => [["1d", 1, "yesterday"], ["1w", 7, "a week ago"]].map(([key, n, words]) => {
    const r = readingAgo(pts, n);
    return { key, v: r ? scale * r.v : null, title: r ? `${words} (${dayDate(r.day, false)}): ${Math.round(scale * r.v)}%` : null };
  });
  return <div className="mt">
    {share != null && <Tile label="Coins in uptrend" tab="breadth" onPick={onPick} aria={`${pct(share)} of coins in uptrend. Open the Uptrend share tab`}
      info={<Info title="Coins in uptrend" paras={[
        "The share of coins the engine calls Uptrend on their daily close. At 55% or more the market is in a broad uptrend (risk-on).",
        "The thin marks show yesterday (1d) and a week ago (1w).",
        below == null ? null : `Today's ${pct(share)} is lower than on ${Math.round(100 * (1 - below))}% of days since 2021.`,
      ].filter(Boolean)} />}>
      <strong>{pct(share)}</strong>
      <Bar v={100 * share} marks={[55]} ago={ago(sharePts, 100)} label={`${pct(share)} of coins in uptrend; the line is 55%`} />
      <em>broad uptrend at 55%</em>
    </Tile>}
    {c && <Tile label={c.kind === "down" ? "Broad downturn" : "Broad uptrend"} tab="cycles" onPick={onPick}
      aria={`Day ${c.today.days}. ${CYCOPY.sooner(c.sooner, c.past.length, c.kind)}. Open the Cycles tab`}
      info={<Info title={c.kind === "down" ? "Broad downturn" : "Broad uptrend"} paras={[...CYCOPY.pop(c.kind), "Point at a dot to see that one; the Cycles chart below lights it."]} />}>
      <strong>Day {c.today.days}</strong>
      <Lengths c={c} onHover={onHoverCycle} />
      <em>{CYCOPY.sooner(c.sooner, c.past.length, c.kind)}</em>
    </Tile>}
    {fg && <Tile label="Fear & Greed" tab="fear" onPick={onPick} aria={`Fear and Greed ${fg.v}. Open its tab`}
      info={<Info title="Fear & Greed" paras={[`The crypto Fear & Greed index, one reading a day: 0 is extreme fear, 100 extreme greed. The lines sit at 25 and 75. This reading: ${dayDate(fg.day)}.`]} />}>
      <strong>{fg.v}</strong>
      <Bar v={fg.v} marks={[25, 75]} tone="orange" label={`Fear and Greed ${fg.v} of 100; lines at 25 and 75`} />
      <em>0 fear · 100 greed</em>
    </Tile>}
    {crowd && <Tile label="Profitable traders" tab="positioning" onPick={onPick}
      aria={`Profitable traders ${pct(crowd.v)} long, ${pct(crowd.S)} short. Open the Positioning tab`}
      info={<Info title="Profitable traders" paras={["The share of the profitable traders' open positions that are long and short, on all coins, at the latest reading.", "The thin marks show where the long share was yesterday (1d) and a week ago (1w)."]} />}>
      <strong><b className="is-long">{pct(crowd.v)}</b><i aria-hidden="true"> · </i><b className="is-short">{pct(crowd.S)}</b></strong>
      <span className="mt-split has-ago" aria-hidden="true">
        <span className="is-long" style={{ flexGrow: crowd.v }} /><span className="is-short" style={{ flexGrow: crowd.S }} />
        <Ago marks={ago(crowdPts, 100)} />
      </span>
      <em>long · short, all coins</em>
    </Tile>}
  </div>;
}
