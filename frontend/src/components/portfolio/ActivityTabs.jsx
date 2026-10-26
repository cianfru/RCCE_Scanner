// B7. Activity: open orders grouped by coin, fills 50 a page, funding per UTC day.
import { useMemo, useState } from "react";
import { displayName } from "../../utils/portfolio/displayNames.js";
import { usd, px, pct, size as fmtSize, stamp, ago, dayKey, dayMonth } from "../../utils/portfolio/format.js";
import { Label, CoinName, pnlClass } from "./parts.jsx";
import { OrderRow, fromMark } from "./OrdersList.jsx";
import { INFO, TABS } from "./copy.js";

function OrderGroups({ orders, marks, canCancel, onCancel, cancelling, names, phone }) {
  const [open, setOpen] = useState(() => new Set());
  const groups = useMemo(() => {
    const by = new Map();
    for (const o of orders) { if (!by.has(o.coin)) by.set(o.coin, []); by.get(o.coin).push(o); }
    return [...by].map(([coin, list]) => {
      const mark = marks.get(coin);
      const tp = list.filter(o => o.isTrigger && String(o.orderType).startsWith("Take Profit")).length;
      const sl = list.filter(o => o.isTrigger && String(o.orderType).startsWith("Stop")).length;
      const near = Math.min(...list.map(o => Math.abs(fromMark(o, mark) ?? Infinity)));
      return { coin, list, mark, tp, sl, limit: list.length - tp - sl, near };
    }).sort((a, b) => a.near - b.near);
  }, [orders, marks]);
  if (!groups.length) return <div className="pf-empty pf-t3">{TABS.none.orders}</div>;
  const toggle = c => setOpen(s => { const n = new Set(s); n.has(c) ? n.delete(c) : n.add(c); return n; });
  return <div className="pf-og">
    {groups.map(g => <div key={g.coin} className="pf-og-g">
      <button type="button" className="pf-og-h" aria-expanded={open.has(g.coin)} onClick={() => toggle(g.coin)}>
        <CoinName coin={g.coin} names={names} size={16} />
        {displayName(g.coin).suffix && <span className="pf-t3">{displayName(g.coin).suffix}</span>}
        <span className="m pf-t2">{g.list.length}</span>
        {!phone && <span className="pf-t3">{[g.tp && TABS.tp(g.tp), g.sl && TABS.sl(g.sl), g.limit && TABS.limits(g.limit)].filter(Boolean).join(" · ")}</span>}
        <span className="pf-t3 m pf-og-near">{Number.isFinite(g.near) ? TABS.nearest(pct(g.near)) : ""}</span>
      </button>
      {open.has(g.coin) && <div className="pf-og-list">
        {!phone && <div className="pf-ord pf-ord-head pf-ord-full"><span>{TABS.cols.type}</span><span>{TABS.cols.side}</span><span>{TABS.cols.trigger}</span><span>{TABS.cols.limit}</span><span>{TABS.cols.size}</span><span>{TABS.cols.reduce}</span><span>{TABS.cols.fromMark}</span><span /></div>}
        {g.list.slice().sort((a, b) => Math.abs(fromMark(a, g.mark) ?? 0) - Math.abs(fromMark(b, g.mark) ?? 0))
          .map(o => <div key={o.oid} className="pf-ord-full-wrap"><OrderRow o={o} mark={g.mark} canCancel={canCancel} onCancel={onCancel} cancelling={cancelling} showSide /></div>)}
      </div>}
    </div>)}
  </div>;
}

function Fills({ fills, names, phone }) {
  const [page, setPage] = useState(0);
  const list = useMemo(() => [...(fills || [])].sort((a, b) => b.time - a.time), [fills]);
  if (!list.length) return <div className="pf-empty pf-t3">{TABS.none.fills}</div>;
  const rows = list.slice(page * 50, page * 50 + 50);
  return <div className="pf-fills">
    {!phone && <div className="pf-fill pf-fill-head"><span>{TABS.cols.time}</span><span>{TABS.cols.coin}</span><span>{TABS.cols.dir}</span><span>{TABS.cols.size}</span><span>{TABS.cols.price}</span><span>{TABS.cols.closedPnl}</span><span>{TABS.cols.fee}</span></div>}
    {rows.map(f => {
      const pnl = parseFloat(f.closedPnl) || 0;
      const name = displayName(f.coin, names).name;
      if (phone) return <div key={`${f.tid}-${f.time}`} className="pf-fill-ph">
        <span className="pf-fp-1"><b className="pf-t1">{name}</b> <span className="pf-t2">{f.dir}</span><span className={`m ${pnlClass(pnl)}`}>{pnl ? usd(pnl, { sign: true }) : ""}</span></span>
        <span className="pf-fp-2 m pf-t3">{stamp(f.time)} · {fmtSize(f.sz)} @ {px(f.px)} · {usd(-(parseFloat(f.fee) || 0), { exact: true })}</span>
      </div>;
      return <div key={`${f.tid}-${f.time}`} className="pf-fill">
        <span className="m pf-t2" title={ago(f.time)}>{stamp(f.time)}</span>
        <span className="pf-t1">{name}{displayName(f.coin).suffix && <span className="pf-t3"> {displayName(f.coin).suffix}</span>}</span>
        <span>{f.dir}</span>
        <span className="m">{fmtSize(f.sz)}</span>
        <span className="m">{px(f.px)}</span>
        <span className={`m ${pnlClass(pnl)}`}>{pnl ? usd(pnl, { sign: true, exact: Math.abs(pnl) < 100 }) : "—"}</span>
        <span className="m pf-t3">{(parseFloat(f.fee) || 0).toFixed(2)}</span>
      </div>;
    })}
    <div className="pf-pager">
      {page > 0 && <button type="button" className="pf-textbtn" onClick={() => setPage(p => p - 1)}>{TABS.newer}</button>}
      {(page + 1) * 50 < list.length && <button type="button" className="pf-textbtn" onClick={() => setPage(p => p + 1)}>{TABS.older}</button>}
    </div>
  </div>;
}

function Funding({ funding, names }) {
  const [open, setOpen] = useState(null);
  const days = useMemo(() => {
    const by = new Map();
    for (const f of funding || []) {
      const k = dayKey(f.time);
      const d = by.get(k) || { key: k, total: 0, coins: new Map() };
      const v = parseFloat(f.delta?.usdc) || 0;
      d.total += v;
      d.coins.set(f.delta?.coin, (d.coins.get(f.delta?.coin) || 0) + v);
      by.set(k, d);
    }
    return [...by.values()].sort((a, b) => (a.key < b.key ? 1 : -1));
  }, [funding]);
  const total = days.reduce((s, d) => s + d.total, 0);
  if (!days.length) return <div className="pf-empty pf-t3">{TABS.none.funding}</div>;
  return <div className="pf-fund">
    <div className="pf-fund-head"><Label info={INFO.funding}>{TABS.d30}</Label><span className={`m ${pnlClass(total)}`}>{usd(total, { sign: true })}</span></div>
    {days.map(d => <div key={d.key} className="pf-fund-g">
      <button type="button" className="pf-fund-row" aria-expanded={open === d.key} onClick={() => setOpen(o => (o === d.key ? null : d.key))}>
        <span className="m pf-t2">{dayMonth(Date.parse(`${d.key}T00:00:00Z`))}</span><span className={`m ${pnlClass(d.total)}`}>{usd(d.total, { sign: true, exact: Math.abs(d.total) < 100 })}</span>
      </button>
      {open === d.key && [...d.coins].sort((a, b) => a[1] - b[1]).map(([c, v]) => <div key={c} className="pf-fund-coin">
        <span>{displayName(c, names).name}</span><span className={`m ${pnlClass(v)}`}>{usd(v, { sign: true, exact: true })}</span></div>)}
    </div>)}
  </div>;
}

export default function ActivityTabs({ tab, onTab, orders, marks, fills, funding, names, canCancel, onCancel, cancelling, phone }) {
  const t = ["orders", "fills", "funding"].includes(tab) ? tab : "orders";
  return <section className="pf-act">
    <div className="pf-act-tabs" role="tablist">
      <button type="button" role="tab" className="te-toggle" aria-pressed={t === "orders"} onClick={() => onTab("orders")}>{TABS.orders} <span className="m pf-t3">{orders.length}</span></button>
      <button type="button" role="tab" className="te-toggle" aria-pressed={t === "fills"} onClick={() => onTab("fills")}>{TABS.fills}</button>
      <button type="button" role="tab" className="te-toggle" aria-pressed={t === "funding"} onClick={() => onTab("funding")}>{TABS.funding}</button>
    </div>
    {t === "orders" && <OrderGroups orders={orders} marks={marks} canCancel={canCancel} onCancel={onCancel} cancelling={cancelling} names={names} phone={phone} />}
    {t === "fills" && <Fills fills={fills} names={names} phone={phone} />}
    {t === "funding" && <Funding funding={funding} names={names} />}
  </section>;
}
