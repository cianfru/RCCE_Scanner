// B3. The checks row: eight plain conditions, each a toggle with the positions it hits; several
// selected filter the board (OR). The board's sort on the right. While the scanner's context is
// missing, the five checks that read it show "—" and are off: unknown, never a false zero.
import HelpTip from "../HelpTip.jsx";
import { CHECK_KEYS, LIQ_FACTS, CTX_CHECKS } from "../../utils/portfolio/checks.js";
import { LiqGlyph } from "./parts.jsx";
import { CHECKS, SORTS } from "./copy.js";

export default function ChecksRow({ counts, selected, onToggle, sort, onSort, phone, hideSort = false, ctxKnown = true }) {
  const unknown = k => !ctxKnown && CTX_CHECKS.has(k);
  const allZero = CHECK_KEYS.every(k => unknown(k) || !counts[k]);
  return <div className={`pf-checks${allZero ? " pf-allzero" : ""}${phone ? " pf-checks-ph" : ""}`}>
    <div className="pf-checks-list" role="group" aria-label="Checks">
      {CHECK_KEYS.map(k => {
        const n = counts[k] || 0;
        const off = unknown(k);
        const tone = off ? "unknown" : !n ? "zero" : LIQ_FACTS.has(k) ? "red" : "on";
        return <HelpTip key={k} width={300} hoverDelay={350} anchorClass="pf-chk" className="pf-chk-wrap"
          buttonProps={{ "aria-pressed": !off && selected.has(k), "data-tone": tone, "aria-disabled": off || undefined }}
          onActivate={() => { if (!off) onToggle(k); }}
          anchor={<>{CHECKS[k].label}<span className="pf-chk-n m">{tone === "red" && <LiqGlyph h={10} />}{off ? "—" : n}</span></>}>
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
