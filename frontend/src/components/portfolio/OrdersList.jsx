// Open orders as text rows: stops and take-profits first by distance from the mark, then each side's
// limit orders collapsed to "12 bids 70.1–76.0" (a click lists them). Cancel only on main-dex orders
// and never on a read-only address.
import { useState } from "react";
import { px, pct, size as fmtSize } from "../../utils/portfolio/format.js";
import { tradable } from "./tradeActions.js";
import { DETAIL, TABS } from "./copy.js";

export function typeWord(o) {
  const t = String(o.orderType || "Limit");
  if (t.startsWith("Take Profit")) return DETAIL.takeProfit;
  if (t === "Stop Market") return DETAIL.stopMarket;
  if (t.startsWith("Stop")) return DETAIL.stopLimit;
  return DETAIL.limit;
}
const priceOf = o => parseFloat(o.isTrigger ? o.triggerPx : o.limitPx);
export const fromMark = (o, mark) => (mark ? (priceOf(o) / mark - 1) * 100 : null);

// Items in display order: triggers by distance, then limit groups (3 or more on one side collapse).
export function orderItems(orders, mark) {
  const trig = orders.filter(o => o.isTrigger).sort((a, b) => Math.abs(fromMark(a, mark) ?? 0) - Math.abs(fromMark(b, mark) ?? 0));
  const items = trig.map(o => ({ kind: "order", o }));
  const sides = ["B", "A"].map(side => orders.filter(o => !o.isTrigger && o.side === side).sort((a, b) => Math.abs(fromMark(a, mark) ?? 0) - Math.abs(fromMark(b, mark) ?? 0)));
  sides.sort((x, y) => Math.abs(fromMark(x[0] || {}, mark) ?? 1e9) - Math.abs(fromMark(y[0] || {}, mark) ?? 1e9));
  for (const list of sides) {
    if (!list.length) continue;
    if (list.length >= 3) items.push({ kind: "group", side: list[0].side, list });
    else for (const o of list) items.push({ kind: "order", o });
  }
  return items;
}

const sizeText = (v, unit, dec) => `${fmtSize(v, dec)}${unit ? ` ${unit}` : ""}`;

export function OrderRow({ o, mark, canCancel, onCancel, cancelling, showSide = false, unit = null, szDecimals = null }) {
  const d = fromMark(o, mark);
  return <div className="pf-ord">
    <span className="pf-ord-t">{typeWord(o)}</span>
    {showSide && <span className="pf-t2">{o.side === "B" ? TABS.buy : TABS.sell}</span>}
    <span className="m pf-t1">{px(priceOf(o))}</span>
    <span className="m pf-t3">{o.isTrigger && o.orderType === "Stop Market" ? `${DETAIL.cap} ${px(o.limitPx)}` : ""}</span>
    <span className="m">{sizeText(o.sz, unit, szDecimals)}</span>
    <span className="pf-t3">{o.reduceOnly ? DETAIL.reduce : ""}</span>
    <span className="m pf-t2">{d != null ? pct(d, { sign: true }) : "—"}</span>
    <span>{canCancel && tradable(o.coin) && <button type="button" className="pf-textbtn pf-cancel" disabled={cancelling === o.oid} onClick={() => onCancel(o.coin, o.oid)}>{DETAIL.cancel}</button>}</span>
  </div>;
}

function GroupRow({ g, mark, canCancel, onCancel, cancelling, unit, szDecimals }) {
  const [open, setOpen] = useState(false);
  const ps = g.list.map(priceOf);
  const lo = Math.min(...ps), hi = Math.max(...ps);
  return <>
    <button type="button" className="pf-ord pf-ord-group" aria-expanded={open} onClick={() => setOpen(v => !v)}>
      <span className="pf-ord-t">{g.side === "B" ? DETAIL.bids(g.list.length) : DETAIL.asks(g.list.length)}</span>
      <span className="m pf-t1">{px(lo)}–{px(hi)}</span>
      <span />
      <span className="m">{sizeText(g.list.reduce((s, o) => s + parseFloat(o.sz), 0), unit, szDecimals)}</span>
      <span className="pf-t3">{g.list.every(o => o.reduceOnly) ? DETAIL.reduce : ""}</span>
      <span className="m pf-t2">{pct(fromMark(g.list[0], mark), { sign: true })}</span>
      <span />
    </button>
    {open && g.list.map(o => <OrderRow key={o.oid} o={o} mark={mark} canCancel={canCancel} onCancel={onCancel} cancelling={cancelling} unit={unit} szDecimals={szDecimals} />)}
  </>;
}

export default function OrdersList({ orders, mark, canCancel, onCancel, cancelling, limit = 6, unit = null, szDecimals = null }) {
  const [all, setAll] = useState(false);
  const items = orderItems(orders, mark);
  const shown = all ? items : items.slice(0, limit);
  const rest = items.slice(shown.length).reduce((s, it) => s + (it.kind === "group" ? it.list.length : 1), 0);
  const p = { mark, canCancel, onCancel, cancelling, unit, szDecimals };
  return <div className="pf-ords">
    {items.length > 0 && <div className="pf-ord pf-ord-head"><span>{DETAIL.cols.type}</span><span>{DETAIL.cols.price}</span><span />
      <span>{DETAIL.cols.size}</span><span /><span>{DETAIL.cols.fromMark}</span><span /></div>}
    {shown.map((it, i) => it.kind === "group"
      ? <GroupRow key={`g${it.side}`} g={it} {...p} />
      : <OrderRow key={it.o.oid ?? i} o={it.o} {...p} />)}
    {rest > 0 && <button type="button" className="pf-textbtn pf-ord-more" onClick={() => setAll(true)}>{DETAIL.moreOrders(rest)}</button>}
  </div>;
}
