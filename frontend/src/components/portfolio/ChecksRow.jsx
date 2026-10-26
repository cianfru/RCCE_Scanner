// B3. The checks row: eight plain conditions, each a toggle with the positions it hits; several
// selected filter the board (OR). The board's sort on the right.
import HelpTip from "../HelpTip.jsx";
import { CHECK_KEYS, LIQ_FACTS } from "../../utils/portfolio/checks.js";
import { CHECKS, SORTS } from "./copy.js";

export default function ChecksRow({ counts, selected, onToggle, sort, onSort, phone, hideSort = false }) {
  const allZero = CHECK_KEYS.every(k => !counts[k]);
  return <div className={`pf-checks${allZero ? " pf-allzero" : ""}${phone ? " pf-checks-ph" : ""}`}>
    <div className="pf-checks-list" role="group" aria-label="Checks">
      {CHECK_KEYS.map(k => {
        const n = counts[k] || 0;
        const tone = !n ? "zero" : LIQ_FACTS.has(k) ? "red" : "on";
        return <HelpTip key={k} width={300} hoverDelay={350} anchorClass="te-toggle pf-chk" className="pf-chk-wrap"
          buttonProps={{ "aria-pressed": selected.has(k), "data-tone": tone }}
          onActivate={() => onToggle(k)}
          anchor={<><span className="pf-chk-l">{CHECKS[k].label}</span><span className="pf-chk-n m">{n}</span></>}>
          <p>{CHECKS[k].info}</p>
        </HelpTip>;
      })}
    </div>
    {!phone && !hideSort && <div className="pf-sorts">{SORTS.map(s => <button key={s.key} type="button" className="te-toggle" aria-pressed={sort === s.key} onClick={() => onSort(s.key)}>{s.label}</button>)}</div>}
  </div>;
}

export function SortRow({ sort, onSort }) {
  return <div className="pf-sorts pf-sorts-ph">{SORTS.map(s => <button key={s.key} type="button" className="te-toggle" aria-pressed={sort === s.key} onClick={() => onSort(s.key)}>{s.label}</button>)}</div>;
}
