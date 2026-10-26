// B4. The board: column labels with their (i), main perps, then TradFi (xyz) and other venues, each
// group collapsed past 8 rows. A row opens its detail inline (B5); an action's outcome sits under it.
import { useState } from "react";
import AsOf from "../AsOf.jsx";
import { Label } from "./parts.jsx";
import { pct } from "../../utils/portfolio/format.js";
import { nearestLiq } from "../../utils/portfolio/checks.js";
import { INFO, LABELS, ROWS } from "./copy.js";

const GROUP_MAX = 8;

export function ActionNotice({ notice, onDismiss }) {
  return <div className="pf-notice pf-row-notice" role={notice.tone === "error" ? "alert" : "status"} data-tone={notice.tone}>
    <span>{notice.text}</span>
    <button type="button" className="te-link" onClick={onDismiss}>{ROWS.dismiss}</button>
  </div>;
}

function Group({ label, rows, render, collapsible = true }) {
  const [all, setAll] = useState(false);
  if (!rows.length) return null;
  const cut = collapsible && !all && rows.length > GROUP_MAX ? GROUP_MAX : rows.length;
  const hidden = rows.slice(cut);
  const near = nearestLiq(hidden, 1)[0];
  return <div className="pf-group">
    {label && <div className="pf-group-h"><span className="pf-lbl pf-lbl-plain">{label}</span><span className="m pf-t3">{rows.length}</span></div>}
    {rows.slice(0, cut).map(render)}
    {hidden.length > 0 && <button type="button" className="pf-group-more" onClick={() => setAll(true)}>
      {ROWS.more(hidden.length)}{near ? ` · ${ROWS.nearestLiq(pct(near.dist.pct, { digits: 0 }))}` : ""}</button>}
  </div>;
}

export default function Board({ groups, phone, showHeld, ctxAsOf, renderRow, renderCard }) {
  if (phone) {
    return <div className="pf-cards">
      <Group rows={groups.main} render={renderCard} />
      <Group label={LABELS.tradfi} rows={groups.xyz} render={renderCard} />
      <Group label={LABELS.other} rows={groups.other} render={renderCard} />
    </div>;
  }
  return <div className={`pf-board${showHeld ? " pf-with-held" : ""}`} role="table">
    <div className="pf-bhead" role="row">
      <span><Label>{LABELS.position}</Label></span>
      <span className="pf-bh-lv"><Label info={INFO.levels} width={360}>{LABELS.levels}</Label><Label info={INFO.toLiq} width={300}>{LABELS.toLiq}</Label></span>
      <span className="pf-bh-sc"><Label info={INFO.scanner} width={340}>{LABELS.scanner}</Label>{ctxAsOf && <AsOf data={ctxAsOf} />}</span>
      {showHeld && <span><Label info={INFO.held}>{LABELS.held}</Label></span>}
      <span><Label info={INFO.traders}>{LABELS.traders}</Label></span>
      <span />
    </div>
    <Group rows={groups.main} render={renderRow} />
    <Group label={LABELS.tradfi} rows={groups.xyz} render={renderRow} />
    <Group label={LABELS.other} rows={groups.other} render={renderRow} />
  </div>;
}

