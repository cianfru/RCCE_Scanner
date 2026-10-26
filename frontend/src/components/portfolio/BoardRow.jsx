// One board row (60 px; a card on phones): POSITION, LEVELS, SCANNER, WHILE HELD, TRADERS and the
// actions. Clicking the row opens its detail below it. Close and Watch use the page's existing
// handlers; Close never shows on a builder-dex row, a read-only address or without a wallet client.
// Colour grammar: green and red are P&L (and the liquidation red); the side reads in plain text.
import { useRef } from "react";
import { Link } from "react-router-dom";
import { Eye, Radar } from "lucide-react";
import { kKey } from "../../utils/tickerRenames.js";
import { displayName } from "../../utils/portfolio/displayNames.js";
import { usd, pct, weekdayTime } from "../../utils/portfolio/format.js";
import { carryShown } from "../../utils/portfolio/checks.js";
import { CoinName, Hover, pnlClass } from "./parts.jsx";
import LevelsRail, { RailSvg, Distance, FlagLine } from "./LevelsRail.jsx";
import ScannerCell, { HeatBar, sigWord, sigColor } from "./ScannerCell.jsx";
import TradersCell, { SplitBar } from "./TradersCell.jsx";
import HeldStrip from "./HeldStrip.jsx";
import { tradable } from "./tradeActions.js";
import { ROWS, STRIP } from "./copy.js";
import useElementWidth from "../../hooks/useElementWidth.js";
import { age } from "../../utils/portfolio/format.js";

function Side({ row }) {
  const sfx = displayName(row.coin).suffix;
  return <span className="pf-side">
    {row.isLong ? ROWS.long : ROWS.short}
    {row.lev != null && <span className="pf-t3 m"> {row.lev}x</span>}
    {row.iso && <span className="pf-t3"> {ROWS.iso}</span>}
    {sfx && <span className="pf-t3"> {sfx}</span>}
  </span>;
}

// The open P&L; hovering shows how it moved since the last visit (this browser's snapshot).
function Pnl({ row, visit, visitT, className = "" }) {
  const body = <span className={`${pnlClass(row.upnl)} ${className}`}>{usd(row.upnl, { sign: true })}</span>;
  if (!visit || visit.side !== row.side || visit.upnl == null || !visitT) return body;
  const d = row.upnl - visit.upnl;
  return <Hover className="pf-pnl-hov" width={220} content={<div className="pf-pop"><div className="pf-pop-row">
    <span>{STRIP.sinceVisit(weekdayTime(visitT))}</span><b className={`m ${pnlClass(d)}`}>{usd(d, { sign: true })}</b></div></div>}>{body}</Hover>;
}

function Carry({ v }) {
  if (v == null) return null;
  return <span className="pf-carry"><span className={pnlClass(v)}>{usd(v, { sign: true })}</span><span className="pf-t3">{STRIP.carry}</span></span>;
}

export function Actions({ row, watching, onWatch, onClose, closing, canClose }) {
  const covered = row.covered && row.venue === "main";
  return <div className="pf-acts" onClick={e => e.stopPropagation()}>
    {covered && <button type="button" className={`pf-icon${watching ? " pf-on" : ""}`} aria-pressed={watching} title={watching ? ROWS.watching : ROWS.watch}
      aria-label={watching ? ROWS.watching : ROWS.watch} onClick={() => onWatch(kKey(row.coin))}><Eye size={16} strokeWidth={1.75} /></button>}
    {covered && <Link className="pf-icon" to={`/radar?tf=4h&focus=${encodeURIComponent(kKey(row.coin))}`} title={ROWS.radar} aria-label={ROWS.radar}><Radar size={16} strokeWidth={1.75} /></Link>}
    {canClose && tradable(row.coin) && <button type="button" className="pf-close" disabled={closing} onClick={e => onClose(row, e.currentTarget)}>{closing ? ROWS.closing : ROWS.close}</button>}
  </div>;
}

export default function BoardRow({ row, names, ev, openAt, watching, onWatch, onClose, closing, canClose, open, onToggle, flash, showHeld, now, dim,
  quietNoStop, visit, visitT, rate }) {
  const carry = carryShown(row, rate);
  return <div className={`pf-row${row.liqFact ? " pf-row-liq" : ""}${open ? " pf-row-open" : ""}${flash ? " pf-row-flash" : ""}${dim ? " pf-dimmed" : ""}`}
    data-coin={row.coin} onClick={onToggle}>
    <button type="button" className="pf-c-pos" aria-expanded={open} onClick={e => { e.stopPropagation(); onToggle(); }}>
      <span className="pf-pos-l1"><CoinName coin={row.coin} names={names} /><Side row={row} /></span>
      <span className="pf-pos-l2 m"><span className="pf-t2">{usd(row.value)}</span>
        <Pnl row={row} visit={visit} visitT={visitT} />
        <span className={`pf-roe ${pnlClass(row.roe)}`}>{pct(row.roe, { sign: true })}</span>
        <Carry v={carry} /></span>
    </button>
    <LevelsRail row={row} quietNoStop={quietNoStop} visitMark={visit?.side === row.side ? visit?.mark : null} />
    {row.covered ? <>
      <ScannerCell row={row} now={now} />
      {showHeld && <HeldStrip ev={ev} from={openAt} now={now / 1000} covered={row.covered} />}
      <TradersCell row={row} />
    </> : <div className="pf-uncov" title={ROWS.notCovered}>{"—"}</div>}
    <Actions row={row} watching={watching} onWatch={onWatch} onClose={onClose} closing={closing} canClose={canClose} />
  </div>;
}

// Phone: a card. Line 1: coin, side and leverage; on the right the P&L with the distance to
// liquidation under it. Line 2: the rail, full width. Line 3: signal and age, heat, traders, one flag.
export function PhoneCard({ row, names, onOpen, now, flash, quietNoStop, visit }) {
  const ref = useRef(null);
  const w = useElementWidth(ref);
  const ctx = row.ctx;
  const since = ctx?.h4?.since ? now / 1000 - ctx.h4.since : null;
  const t = ctx?.traders;
  return <button type="button" className={`pf-card2${row.liqFact ? " pf-row-liq" : ""}${flash ? " pf-row-flash" : ""}`} data-coin={row.coin} onClick={onOpen}>
    <span className="pf-cd-l1"><span className="pf-cd-name"><CoinName coin={row.coin} names={names} /><Side row={row} /></span>
      <span className="pf-cd-r"><span className={`m pf-cd-pnl ${pnlClass(row.upnl)}`}>{usd(row.upnl, { sign: true })}</span>
        {row.dist && <Distance dist={row.dist} className="pf-cd-dist" />}</span></span>
    <span ref={ref} className="pf-cd-rail"><RailSvg row={row} width={w} height={36} compact visitMark={visit?.side === row.side ? visit?.mark : null} /></span>
    <span className="pf-cd-l3">
      {ctx?.h4 ? <><span className="pf-sig" style={{ color: sigColor(ctx.h4.signal) }}>{sigWord(ctx.h4.signal)}</span>
        {since != null && <span className="pf-t3 m">{age(since)}</span>}
        <HeatBar heat={ctx.h4.heat} prev={ctx.h4.heat_prev} w={32} /><span className="m pf-t2">{ctx.h4.heat}</span></> : <span className="pf-t4">{"—"}</span>}
      {t && (t.long.n || t.short.n) ? <span className="pf-cd-tr"><SplitBar l={t.long.n || 0} s={t.short.n || 0} w={24} h={3} />
        <span className="m"><span className="pf-long">{t.long.n}</span><span className="pf-t4"> · </span><span className="pf-short">{t.short.n}</span></span></span> : null}
      <FlagLine row={row} quietNoStop={quietNoStop} />
    </span>
  </button>;
}
