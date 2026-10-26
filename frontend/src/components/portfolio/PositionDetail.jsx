// B5. A row's detail: the chart on the left (as tall as the facts beside it, 340 px at least), the
// facts and the orders on the coin on the right.
import { useLayoutEffect, useRef, useState } from "react";
import { REGIME_META } from "../../theme.js";
import { usd, px, pct, size as fmtSize, stamp, dayMonth, age } from "../../utils/portfolio/format.js";
import { displayName } from "../../utils/portfolio/displayNames.js";
import { Hover, LiqGlyph, pnlClass } from "./parts.jsx";
import PositionChart from "./PositionChart.jsx";
import OrdersList from "./OrdersList.jsx";
import { sigWord, sigColor } from "./ScannerCell.jsx";
import { useAssetCtx } from "./assetCtx.js";
import { DETAIL } from "./copy.js";

export { useAssetCtx };

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

export function Facts({ row, trip, ev, openAt, windowStart, nowS }) {
  const a = useAssetCtx(row.coin);
  const name = displayName(row.coin).name;
  const t = row.ctx?.traders?.[row.side];
  const carry = a && Number.isFinite(a.funding) ? -(row.isLong ? 1 : -1) * a.funding * row.value * 24 : null;
  const fundShare = row.upnl ? Math.abs(row.funding / (Math.abs(row.upnl) + Math.abs(row.funding))) * 100 : null;
  const before = !openAt;
  const realised = trip && !before ? trip.realized + trip.fees : null;
  const ao = atOpen(ev, openAt);
  const liqRed = row.dist && row.dist.pct < 15;
  const f = (k, v, cls = "") => <div className="pf-fact" key={k}><span className="pf-fact-k">{k}</span><span className={`pf-fact-v m ${cls}`}>{v}</span></div>;
  return <div className="pf-facts">
    {f(DETAIL.size, `${fmtSize(Math.abs(row.szi), a?.szDecimals)} ${name}`)}
    {f(DETAIL.value, usd(row.value))}
    {f(DETAIL.entry, px(row.entry))}
    {f(DETAIL.mark, px(row.mark))}
    {f(DETAIL.liq, row.liq ? <>{liqRed && <LiqGlyph h={11} />}{px(row.liq)} · {pct(row.dist?.pct, { digits: 0 })}</> : "—", liqRed ? "pf-red" : "")}
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
      <span className="pf-sig" style={{ color: sigColor(ao.sig) }}>{sigWord(ao.sig)}</span><span className="pf-t3">{"4H · "}</span><span>{REGIME_META[ao.reg]?.name || ao.reg}</span></span></div>}
    {t?.median_entry ? f(DETAIL.tradersEntry, `${px(t.median_entry)} · ${DETAIL.you} ${pct((row.entry / t.median_entry - 1) * 100, { sign: true })}`) : null}
    {t?.n ? f(DETAIL.inProfit, `${t.in_profit} ${DETAIL.of} ${t.n}`) : null}
  </div>;
}

const CHART_MIN = 340, CHART_MAX = 560, CHART_TOP = 26;

export default function PositionDetail({ row, classified, trip, ev, openAt, windowStart, canCancel, onCancel, cancelling, phone }) {
  const nowS = Date.now() / 1000;
  const mine = row.orders || [];
  const a = useAssetCtx(row.coin);
  // Desktop: the chart takes the facts column's height (340 to 560 px).
  const side = useRef(null);
  const [h, setH] = useState(CHART_MIN);
  useLayoutEffect(() => {
    if (phone || !side.current) return undefined;
    const fit = () => side.current && setH(Math.max(CHART_MIN, Math.min(CHART_MAX, Math.round(side.current.getBoundingClientRect().height - CHART_TOP))));
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(side.current);
    return () => ro.disconnect();
  }, [phone]);
  return <div className={`pf-detail${phone ? " pf-detail-ph" : ""}`} onClick={e => e.stopPropagation()}>
    <div className="pf-detail-chart"><PositionChart row={row} classified={classified} events={ev} openAt={openAt} height={phone ? 220 : h} phone={phone} szDecimals={a?.szDecimals} /></div>
    <div className="pf-detail-side" ref={side}>
      <Facts row={row} trip={trip} ev={ev} openAt={openAt} windowStart={windowStart} nowS={nowS} />
      <div className="pf-ords-h">{DETAIL.ordersOn(displayName(row.coin).name, mine.length)}</div>
      {row.venue !== "main" && !row.ordersRead ? <div className="pf-t3">{"—"}</div>
        : <OrdersList orders={mine} mark={row.mark} canCancel={canCancel} onCancel={onCancel} cancelling={cancelling} unit={displayName(row.coin).name} szDecimals={a?.szDecimals} />}
    </div>
  </div>;
}
