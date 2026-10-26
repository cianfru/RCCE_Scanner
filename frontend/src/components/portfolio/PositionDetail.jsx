// B5. A row's detail: the chart on the left, the facts and the orders on the coin on the right.
import { useEffect, useState } from "react";
import * as hlClient from "../../services/hlClient.js";
import { REGIME_META, SIGNAL_META } from "../../theme.js";
import { usd, px, pct, size as fmtSize, stamp, dayMonth, age } from "../../utils/portfolio/format.js";
import { displayName, venueOf } from "../../utils/portfolio/displayNames.js";
import { Hover, pnlClass } from "./parts.jsx";
import PositionChart from "./PositionChart.jsx";
import OrdersList from "./OrdersList.jsx";
import { sigWord } from "./ScannerCell.jsx";
import { DETAIL } from "./copy.js";

// metaAndAssetCtxs per dex, cached for five minutes: szDecimals and the current funding rate.
const metaCache = new Map();
export function useAssetCtx(coin) {
  const dex = venueOf(coin) === "main" ? "" : venueOf(coin);
  const [v, setV] = useState(() => metaCache.get(dex)?.v || null);
  useEffect(() => {
    const hit = metaCache.get(dex);
    if (hit && Date.now() - hit.at < 300_000) { setV(hit.v); return undefined; }
    let alive = true;
    hlClient.getMetaAndAssetCtxs(dex).then(raw => {
      const [meta, ctxs] = raw || [];
      const out = new Map();
      (meta?.universe || []).forEach((u, i) => out.set(u.name, { szDecimals: u.szDecimals, funding: parseFloat(ctxs?.[i]?.funding) }));
      metaCache.set(dex, { at: Date.now(), v: out });
      if (alive) setV(out);
    }).catch(() => {});
    return () => { alive = false; };
  }, [dex]);
  return v?.get(coin) || null;
}

// What the scanner read when the position opened (from the events body).
export function atOpen(ev, openAt) {
  if (!ev?.at_start || !openAt || openAt < ev.windowStart) return null;
  let sig = ev.at_start.h4?.signal, reg = ev.at_start.h4?.regime;
  for (const e of ev.events || []) {
    if (e.t > openAt || e.tf !== "4h") continue;
    if (e.kind === "signal") sig = e.to; else reg = e.to;
  }
  return { sig, reg };
}

export function Facts({ row, trip, fundingSince, ev, openAt, windowStart, nowS }) {
  const a = useAssetCtx(row.coin);
  const name = displayName(row.coin).name;
  const t = row.ctx?.traders?.[row.side];
  const carry = a && Number.isFinite(a.funding) ? -(row.isLong ? 1 : -1) * a.funding * row.value * 24 : null;
  const fundShare = row.upnl ? Math.abs(row.funding / (Math.abs(row.upnl) + Math.abs(row.funding))) * 100 : null;
  const before = !openAt;
  const realised = trip && !before ? trip.realized + trip.fees : null;
  const ao = atOpen(ev, openAt);
  const f = (k, v, cls = "") => <div className="pf-fact" key={k}><span className="pf-fact-k">{k}</span><span className={`pf-fact-v m ${cls}`}>{v}</span></div>;
  return <div className="pf-facts">
    {f(DETAIL.size, `${fmtSize(Math.abs(row.szi), a?.szDecimals)} ${name}`)}
    {f(DETAIL.value, usd(row.value))}
    {f(DETAIL.entry, px(row.entry))}
    {f(DETAIL.mark, px(row.mark))}
    {f(DETAIL.liq, row.liq ? `${px(row.liq)} · ${pct(row.dist?.pct, { digits: 0 })}` : "—", row.dist && row.dist.pct < 15 ? "pf-red" : "")}
    {f(DETAIL.margin, `${usd(row.margin)} · ${row.iso ? DETAIL.isolated : DETAIL.cross}`)}
    <div className="pf-fact"><span className="pf-fact-k">{DETAIL.funding}</span>
      <Hover className={`pf-fact-v m ${pnlClass(row.funding)}`} width={200} content={fundShare != null ? <div className="pf-pop"><div className="pf-pop-row"><span>{DETAIL.pnlShare}</span><b className="m">{pct(fundShare, { digits: 0 })}</b></div></div> : null}>
        {usd(row.funding, { sign: true })}</Hover></div>
    {f(DETAIL.carry, carry != null ? `${usd(carry, { sign: true })}${DETAIL.perDay}` : "—", pnlClass(carry))}
    {f(DETAIL.opened, before ? DETAIL.before(dayMonth((windowStart || nowS - 30 * 86400) * 1000)) : `${stamp(openAt * 1000)} · ${age(nowS - openAt, { long: true })}`)}
    {f(DETAIL.addsTrims, trip && !before ? `${trip.adds} · ${trip.trims}` : "—")}
    {f(DETAIL.realised, realised != null ? usd(realised, { sign: true }) : "—", pnlClass(realised))}
    {f(DETAIL.fees, trip && !before ? usd(-trip.fees) : "—", trip?.fees ? "pf-dn" : "")}
    {ao && <div className="pf-fact"><span className="pf-fact-k">{DETAIL.atOpen}</span><span className="pf-fact-v">
      <span style={{ color: SIGNAL_META[ao.sig]?.color }}>{sigWord(ao.sig)}</span> <span className="pf-t3">4H ·</span> {REGIME_META[ao.reg]?.name || ao.reg}</span></div>}
    {t?.median_entry ? f(DETAIL.tradersEntry, `${px(t.median_entry)} · ${DETAIL.you} ${pct((row.entry / t.median_entry - 1) * 100, { sign: true })}`) : null}
    {t?.n ? f(DETAIL.inProfit, `${t.in_profit} ${DETAIL.of} ${t.n}`) : null}
  </div>;
}

export default function PositionDetail({ row, classified, trip, ev, openAt, windowStart, canCancel, onCancel, cancelling, phone, fundingSince }) {
  const nowS = Date.now() / 1000;
  const mine = row.orders || [];
  return <div className={`pf-detail${phone ? " pf-detail-ph" : ""}`} onClick={e => e.stopPropagation()}>
    <div className="pf-detail-chart"><PositionChart row={row} classified={classified} events={ev} openAt={openAt} height={phone ? 220 : 300} /></div>
    <div className="pf-detail-side">
      <Facts row={row} trip={trip} fundingSince={fundingSince} ev={ev} openAt={openAt} windowStart={windowStart} nowS={nowS} />
      <div className="pf-ords-h">{DETAIL.ordersOn(displayName(row.coin).name, mine.length)}</div>
      {row.venue !== "main" && !row.ordersRead ? <div className="pf-t3">{"—"}</div>
        : <OrdersList orders={mine} mark={row.mark} canCancel={canCancel} onCancel={onCancel} cancelling={cancelling} />}
    </div>
  </div>;
}
