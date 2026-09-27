import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import HelpTip from "./HelpTip.jsx";
import SetupPair from "./SetupPair.jsx";
import SparklineCell from "./SparklineCell.jsx";
import TokenLogo from "./TokenLogo.jsx";
import { REGIME_META, SIGNAL_META, col, getBaseSymbol } from "../theme.js";
import { SIDE_COLOR, fmtPx, fmtUsd } from "../utils/traderFormat.js";
import { briefRows, fmtAgo, medianGap, setupSide } from "../utils/intel.js";
import { CROWD_COLOR, Pin, WATCH_TIP } from "./radar/shared.jsx";

// Current price against where each group got in: median entries per side and the
// profitable traders' opens of the last 24h. Log scale so a wide range still reads.
function PriceRuler({ intel, mark, gap }) {
  const p = intel.profitable || {}, l = intel.large || {};
  const marks = [
    p.long?.median_entry && { v: p.long.median_entry, label: `Profitable long ${fmtPx(p.long.median_entry)}`, color: SIDE_COLOR.long, row: 0 },
    p.short?.median_entry && { v: p.short.median_entry, label: `Profitable short ${fmtPx(p.short.median_entry)}`, color: SIDE_COLOR.short, row: 0 },
    l.long?.median_entry && { v: l.long.median_entry, label: `Large long ${fmtPx(l.long.median_entry)}`, color: SIDE_COLOR.long, row: 1, square: true },
    l.short?.median_entry && { v: l.short.median_entry, label: `Large short ${fmtPx(l.short.median_entry)}`, color: SIDE_COLOR.short, row: 1, square: true },
  ].filter(Boolean);
  const dots = (intel.recent || []).filter(o => o.px > 0);
  const vals = [mark, ...marks.map(m => m.v), ...dots.map(o => o.px)].filter(v => v > 0);
  if (!mark || vals.length < 2) return null;
  const lo = Math.log(Math.min(...vals)), hi = Math.log(Math.max(...vals));
  const pad = (hi - lo) * 0.08 || 0.02;
  const x = v => `${(((Math.log(v) - (lo - pad)) / (hi - lo + 2 * pad)) * 100).toFixed(2)}%`;
  return (
    <figure className="si-ruler" aria-label="Current price against traders' entries">
      {gap && <p className="si-gap">{gap}</p>}
      <div className="si-track">
        <div className="si-lane si-lane-pro" />
        <div className="si-lane si-lane-large" />
        {dots.map((o, i) => <i key={i} className={o.cohort === "profitable" ? "si-dot" : "si-dot si-dot-large"}
          style={{ left: x(o.px), background: col(SIDE_COLOR[o.side]) }} />)}
        {marks.map((m, i) => <i key={i} className={m.row ? "si-med si-med-large" : "si-med"} style={{ left: x(m.v), background: col(m.color) }} />)}
        <i className="si-now" style={{ left: x(mark) }} />
      </div>
      <div className="si-ends" aria-hidden="true"><span>{fmtPx(Math.exp(lo - pad))}</span><span>{fmtPx(Math.exp(hi + pad))}</span></div>
      <figcaption>
        <span><i className="si-key si-key-mark" />Price {fmtPx(mark)}</span>
        {marks.map((m, i) => <span key={i}><i className="si-key" style={{ background: col(m.color) }} />{m.label}</span>)}
        {dots.length > 0 && <span className="si-dim">Dots: opens in the last 24h (top row profitable, bottom row large)</span>}
      </figcaption>
    </figure>
  );
}

function SideBar({ label, group }) {
  const L = group?.long?.n || 0, S = group?.short?.n || 0, n = L + S;
  return (
    <div className="si-side">
      <div className="si-side-label">{label}</div>
      {n ? <>
        <div className="tc-bar"><i style={{ width: `${Math.round((100 * L) / n)}%`, background: col(SIDE_COLOR.long) }} /><i style={{ flex: 1, background: col(SIDE_COLOR.short) }} /></div>
        <div className="tc-split"><span>{L} long · {fmtUsd(group.long.usd)}</span><span>{S} short · {fmtUsd(group.short.usd)}</span></div>
      </> : <p className="si-dim">None hold it.</p>}
    </div>
  );
}

// Everything behind a setup, in one place: the engine's reading and timing as key/value
// rows (named like the Radar's focus panel), and what tracked traders hold and opened.
// Opens from the Radar's "Full detail". Watch and the chart link sit at the top.
export default function SetupIntelDrawer({ row, intel, updatedAt, watching = false, onWatch, onOpenChart, onClose }) {
  const closeRef = useRef(null);
  const opener = useRef(typeof document !== "undefined" ? document.activeElement : null);
  useEffect(() => {
    closeRef.current?.focus();
    const prev = opener.current;
    const onKey = e => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = overflow; prev?.focus?.(); };
  }, [onClose]);

  const coin = getBaseSymbol(row.symbol);
  const now = Date.now();
  const side = setupSide(row);
  const rows = briefRows(row, intel, now, {
    regimeName: k => (REGIME_META[k] || REGIME_META.FLAT).name,
    signalLabel: k => SIGNAL_META[k]?.label || k,
    fmt: fmtPx,
  });
  const warnings = row.signal_warnings || [];
  // One price: the live mark with its reading time when traders' data is in, else the scan's.
  const price = intel?.mark || row.price;
  const at = intel?.mark ? updatedAt : row.evaluated_at;
  const atText = at ? new Date(at * 1000).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) : null;

  return createPortal(<div className="reflex-terminal">
    <div className="mh-backdrop" onClick={onClose} />
    <aside className="mh-drawer si" role="dialog" aria-modal="true" aria-labelledby="si-title">
      <header className="mh-head">
        <h2 id="si-title" className="si-title"><TokenLogo symbol={row.symbol} size={24} />{coin}<span>{String(row.timeframe || "").toUpperCase()} · {fmtPx(price)}{atText && <em> at {atText}</em>}</span></h2>
        <button ref={closeRef} type="button" className="mh-close" onClick={onClose}>Close</button>
      </header>
      <div className="mh-body">
        <div className="si-actions">
          {onWatch && <button type="button" className="smap-watch" aria-pressed={watching} title={WATCH_TIP} onClick={onWatch}>
            <Pin color={watching ? "var(--t-bg)" : "var(--t-accent)"} />{watching ? "Watching" : "Watch"}</button>}
          <button type="button" className="te-link" onClick={() => onOpenChart(row)}>Open {coin} chart</button>
        </div>
        <div className="si-top">
          <SetupPair row={row} transition />
          {row.sparkline?.length > 1 && <SparklineCell data={row.sparkline} width={120} height={32} />}
        </div>

        <dl className="smap-kv smap-kv-rows si-rows">
          {rows.map(r => <div key={r.k}><dt>{r.k}</dt><dd>
            {r.k === "Crowd" && r.label ? <><strong style={{ color: col(CROWD_COLOR[r.key] || CROWD_COLOR.holding) }}>{r.label}</strong> {r.v} <HelpTip title="How the crowd is read">
              <p>Profitable traders relative to this setup{side ? ` (${side})` : ""}. Quiet: none hold it. Against: two or more hold the other side and outnumber this side. Crowded: eight or more on this side, or three or more with price 15% or more past their median entry. Early: at least one opened on this side in the last 24 hours, near today's price. Holding: anything else.</p>
              <p>Over the last 180 days, profitable traders mostly opened after moves rather than before them, and two of them converging on a coin did not lead price. This describes the crowd; it is not a signal.</p>
            </HelpTip></> : r.v}
          </dd></div>)}
        </dl>

        {intel && <>
          <h3 className="si-h">Where they got in</h3>
          <PriceRuler intel={intel} mark={intel.mark || row.price} gap={medianGap(row, intel)} />
          <div className="si-sides">
            <SideBar label="Profitable traders" group={intel.profitable} />
            <SideBar label="Large accounts" group={intel.large} />
          </div>

          <h3 className="si-h">Opened in the last 24h</h3>
          {intel.recent?.length ? <ul className="si-opens">
            {intel.recent.map((o, i) => <li key={i}>
              <span className="si-dim">{fmtAgo(o.t, now)}</span>
              <span>{o.cohort === "profitable" ? "Profitable" : "Large"}</span>
              <span style={{ color: col(SIDE_COLOR[o.side]) }}>{o.side}</span>
              <span>{fmtPx(o.px)}</span>
              <span className="si-dim">{fmtUsd(o.usd)}</span>
            </li>)}
          </ul> : <p className="si-dim">No tracked wallet opened a position here in the last 24h.</p>}
        </>}
        {!intel && <p className="si-dim">Trader positioning is not in yet.</p>}

        {warnings.length > 0 && <>
          <h3 className="si-h">Context notes</h3>
          <ul className="si-brief si-notes">{warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
        </>}

        <div className="si-foot">
          <p className="si-dim">Positions are what these wallets hold at their latest reading (about every 30 minutes); opens are timed to the nearest reading. You decide the trade.</p>
        </div>
      </div>
    </aside>
  </div>, document.body);
}
