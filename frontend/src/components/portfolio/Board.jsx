// B4. The board: column labels with their (i), main perps, then TradFi (xyz) and other venues, each
// group collapsed past 8 rows. A row opens its detail inline (B5); an action's outcome sits under it.
import AsOf from "../AsOf.jsx";
import { Label } from "./parts.jsx";
import { pct } from "../../utils/portfolio/format.js";
import { nearestLiq } from "../../utils/portfolio/checks.js";
import { INFO, LABELS, ROWS } from "./copy.js";

export const GROUP_MAX = 8;
// The rows a group shows: the first GROUP_MAX until "+n more" opens it (all: it was opened).
export const groupShown = (rows, all) => (!all && rows.length > GROUP_MAX ? rows.slice(0, GROUP_MAX) : rows);

export function ActionNotice({ notice, onDismiss }) {
  return <div className="pf-notice pf-row-notice" role={notice.tone === "error" ? "alert" : "status"} data-tone={notice.tone}>
    <span>{notice.text}</span>
    <button type="button" className="te-link" onClick={onDismiss}>{ROWS.dismiss}</button>
  </div>;
}

function Group({ label, rows, render, all, onAll }) {
  if (!rows.length) return null;
  const cut = groupShown(rows, all).length;
  const hidden = rows.slice(cut);
  const near = nearestLiq(hidden, 1)[0];
  return <div className="pf-group">
    {label && <div className="pf-group-h"><span className="pf-lbl pf-lbl-plain">{label}</span><span className="m pf-t3">{rows.length}</span></div>}
    {rows.slice(0, cut).map(render)}
    {hidden.length > 0 && <button type="button" className="pf-group-more" onClick={onAll}>
      {ROWS.more(hidden.length)}{near ? ` · ${ROWS.nearestLiq(pct(near.dist.pct, { digits: 0 }))}` : ""}</button>}
  </div>;
}

// expanded: the groups ("main", "xyz", "other") opened past GROUP_MAX. The page keeps it, so it knows
// which rows are on screen (an action's notice sits under its row only while that row is shown).
export default function Board({ groups, phone, showHeld, ctxAsOf, renderRow, renderCard, expanded, onExpand }) {
  const g = (key, label, render) => <Group label={label} rows={groups[key]} render={render} all={expanded.has(key)} onAll={() => onExpand(key)} />;
  if (phone) {
    return <div className="pf-cards">
      {g("main", null, renderCard)}
      {g("xyz", LABELS.tradfi, renderCard)}
      {g("other", LABELS.other, renderCard)}
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
    {g("main", null, renderRow)}
    {g("xyz", LABELS.tradfi, renderRow)}
    {g("other", LABELS.other, renderRow)}
  </div>;
}

