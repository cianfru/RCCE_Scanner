// B2. Since: what changed since the last visit (or in 24 hours). A fixed first cell, then up to four
// change cells; the rest behind "+n". A cell scrolls to its row.
import { useState } from "react";
import { REGIME_META } from "../../theme.js";
import { Label, Hover, CoinLogo, NameSfx, LiqGlyph, pnlClass } from "./parts.jsx";
import { sigWord, sigColor } from "./ScannerCell.jsx";
import { usd, pct, weekdayTime } from "../../utils/portfolio/format.js";
import { INFO, LABELS, SINCE, RAIL, ROWS } from "./copy.js";

const sideWord = s => (s === "short" ? ROWS.short.toLowerCase() : ROWS.long.toLowerCase());

function Cell({ c, onPick }) {
  const name = <NameSfx coin={c.coin} />;
  const logo = <CoinLogo coin={c.coin} size={14} />;
  let body;
  if (c.kind === "signal") {
    body = <><span className="pf-sc-k">{name} {c.tf === "h4" ? "4H" : "1D"}</span>
      <s className="pf-sc-old">{sigWord(c.from)}</s><span className="pf-sc-new" style={{ color: sigColor(c.to) }}>{sigWord(c.to)}</span></>;
  } else if (c.kind === "heat") {
    body = <><span className="pf-sc-k">{name} {SINCE.heat}</span>
      <span className="pf-heatmini" aria-hidden="true"><i className="pf-hm-ghost" style={{ left: `${Math.min(100, c.from)}%` }} /><i className="pf-hm-now" style={{ left: `${Math.min(100, c.to)}%` }} /></span>
      <span className="m pf-sc-v">{c.from} → {c.to}</span></>;
  } else if (c.kind === "liq") {
    body = <><span className="pf-sc-k">{name} {SINCE.liq}</span><span className="m pf-sc-v">{pct(c.from, { digits: 0 })} → <span className={c.red ? "pf-red" : ""}>{c.red && <LiqGlyph h={10} />}{pct(c.to, { digits: 0 })}</span></span></>;
  } else if (c.kind === "band") {
    body = <><span className="pf-sc-k">{name} {SINCE.band}</span><span className="pf-sc-v">{RAIL.bandState[c.from] || c.from} → {RAIL.bandState[c.to] || c.to}</span></>;
  } else if (c.kind === "regime") {
    body = <><span className="pf-sc-k">{name} 4H</span><s className="pf-sc-old">{REGIME_META[c.from]?.name || c.from}</s><span className="pf-sc-v pf-t1">{REGIME_META[c.to]?.name || c.to}</span></>;
  } else if (c.kind === "traders") {
    const pair = ([l, s]) => <><span className="pf-long">{l ?? 0}</span> · <span className="pf-short">{s ?? 0}</span></>;
    body = <><span className="pf-sc-k">{name} {SINCE.traders}</span><span className="m pf-sc-v">{pair(c.from)} → {pair(c.to)}</span></>;
  } else if (c.kind === "trip") {
    body = c.opened ? <span className="pf-sc-k">{SINCE.opened} {name} {sideWord(c.side)}</span>
      : <><span className="pf-sc-k">{SINCE.closed} {name} {sideWord(c.side)}</span>{c.pnl != null && <span className={`m pf-sc-v ${pnlClass(c.pnl)}`}>{usd(c.pnl, { sign: true })}</span>}</>;
  } else if (c.kind === "price") {
    body = <><span className="pf-sc-k">{name}</span><span className={`m pf-sc-v ${pnlClass(c.change)}`}>{pct(c.change, { sign: true })}</span></>;
  }
  return <button type="button" className="pf-scell" onClick={() => onPick?.(c.coin)}>{logo}{body}</button>;
}

export default function SinceRow({ mode, onMode, summary, changes, onPick, phone, hasBase }) {
  const [open, setOpen] = useState(false);
  const shown = changes.slice(0, 4), rest = changes.slice(4);
  const head = summary ? <span className="pf-since-when"><span className="pf-t1">{weekdayTime(summary.t)}</span>
    <span className="m"><span className={pnlClass(summary.pnl)}>{usd(summary.pnl, { sign: true })}</span>{summary.fills != null && <span className="pf-t2"> · {SINCE.fills(summary.fills)}</span>}</span></span> : null;
  const toggle = <span className="pf-since-modes">
    <button type="button" className="te-toggle" aria-pressed={mode === "visit"} disabled={!hasBase} onClick={() => onMode("visit")}>{SINCE.lastVisit}</button>
    <span className="pf-sep" aria-hidden="true">·</span>
    <button type="button" className="te-toggle" aria-pressed={mode === "24h"} onClick={() => onMode("24h")}>{SINCE.h24}</button>
  </span>;
  if (phone) {
    return <div className="pf-since pf-since-ph">
      <button type="button" className="pf-since-line" aria-expanded={open} onClick={() => setOpen(o => !o)}>
        <span className="pf-lbl pf-lbl-plain">{LABELS.since}</span>
        {summary && <span className="pf-t1">{weekdayTime(summary.t)}</span>}
        {summary && <span className={`m ${pnlClass(summary.pnl)}`}>{usd(summary.pnl, { sign: true })}</span>}
        <span className="pf-t3">{changes.length ? SINCE.changes(changes.length) : SINCE.nothing}</span>
      </button>
      {open && <div className="pf-since-stack">{toggle}{changes.map((c, i) => <Cell key={i} c={c} onPick={onPick} />)}</div>}
    </div>;
  }
  return <div className="pf-since">
    <div className="pf-since-first">
      <div className="pf-since-l1"><Label info={mode === "24h" ? INFO.since24 : INFO.since}>{LABELS.since}</Label>{toggle}</div>
      <div className="pf-since-l2">{head}</div>
    </div>
    <div className="pf-since-cells">
      {changes.length === 0 ? <span className="pf-t3 pf-quiet">{SINCE.nothing}</span>
        : shown.map((c, i) => <Cell key={i} c={c} onPick={onPick} />)}
      {rest.length > 0 && <Hover className="pf-since-more" tabIndex={0} width={280}
        content={<div className="pf-pop pf-pop-cells">{rest.map((c, i) => <Cell key={i} c={c} onPick={onPick} />)}</div>}>
        <span className="pf-t3">+{rest.length}</span>
      </Hover>}
    </div>
  </div>;
}
