import { traderLean } from "../utils/traders.js";
import HelpTip from "./HelpTip.jsx";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Star } from "lucide-react";
import { setupAlignment, marketWideMissing } from "../utils/signalPresentation.js";
import { SECTOR_SHORT } from "../utils/sectors.js";
import { formatPrice } from "../utils/marketPresentation.js";
import { marketHref } from "../utils/researchNavigation.js";
import { fitColumns, widthCaps } from "../utils/gridFit.js";
import useElementWidth from "../hooks/useElementWidth.js";
import { COLUMN_FIT } from "../scannerColumns.js";
import SetupPair, { setupColor } from "./SetupPair.jsx";
import TokenLogo from "./TokenLogo.jsx";
import RegimeTransition from "./RegimeTransition.jsx";
import { T, m, col, REGIME_META, fmt, getBaseSymbol, exhaustMeta } from "../theme.js";
import { TableSkeleton } from "./Skeleton.jsx";
import {
  ZScoreBar, RegimeBadge, SignalDot, DivergencePill,
  HeatCell, ExhaustBadge, FundingCell, OITrendBadge, ConfluenceBadge, CVDBadge,
  SmartMoneyBadge,
} from "./badges.jsx";
import SparklineCell from "./SparklineCell.jsx";
import InfoButton, { COLUMN_INFO, ColumnHelp } from "./InfoPopover.jsx";
import GlassCard from "./GlassCard.jsx";
import { useWallet } from "../WalletContext.jsx";
import useMyPositions from "../hooks/useMyPositions.js";
import { pnl } from "../utils/setupMap.js";
import { sideColor, fmtPx } from "../utils/traderFormat.js";

// Optional columns hidden while every row in view would show only a dash, so the
// grid carries no dead columns (e.g. no divergences or exhaustion states today).
const EMPTY_WHEN = {
  DIV: r => !r.divergence,
  EXHAUST: r => !r.exhaustion_state || r.exhaustion_state === "NEUTRAL",
  SM: r => !["long", "short"].includes(traderLean(r.smart_money?.profitable).side),
  OI: r => !r.positioning?.oi_trend || ["STABLE", "UNKNOWN"].includes(r.positioning.oi_trend),
  CVD: r => !r.cvd_trend || ["NEUTRAL", "UNAVAILABLE"].includes(r.cvd_trend),
};

// Plain names for the Column guide's "hidden to fit" line.
const SHORT_NAME = { "#": "#", "Z-SCORE": "Z-score", SPARK: "Spark", COND: "Cond", HEAT: "Heat", CVD: "CVD", CONF: "Conf",
  DIV: "Div", EXHAUST: "Exhaust", ENERGY: "Energy", SM: "SM", OI: "OI" };
const ALIGNED_TITLE = "Group aligned regime and signal setups first, preserving the selected order within each strength. Does not change engine scores.";
const NO_REF = { current: null };
const DASH = <span style={{ color: T.text4 }}>{"—"}</span>;

// "24 days +8.4%": the sparkline's span (24 closes) and its change; ENERGY folds in when its column is hidden.
function sparkTitle(row, timeframe, withEnergy) {
  const d = row.sparkline;
  if (!d?.length) return undefined;
  const hours = d.length * (timeframe === "4h" ? 4 : 24);
  const span = hours % 24 === 0 ? `${hours / 24} days` : `${hours}h`;
  const pct = d[0] ? (d[d.length - 1] / d[0] - 1) * 100 : null;
  let text = pct == null ? span : `${span} ${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`;
  if (withEnergy && row.history_bars !== 0 && row.energy != null) text += ` · energy ${fmt(row.energy, 2)}`;
  return text;
}

// The exhaustion word for the HEAT phase line, when the EXHAUST column is hidden and the row has a state.
function exhaustFold(row) {
  const state = row.exhaustion_state;
  if (!state || state === "NEUTRAL") return null;
  const meta = exhaustMeta(state);
  if (meta.text === "—") return null;
  const floor = state === "FLOOR" || state === "EXHAUSTED_FLOOR";
  return floor && row.floor_confirmed ? { text: "FLOOR ✓", color: col("#34d399") } : { text: meta.text, color: meta.color };
}

// "Your short from 84,765 · +3.1%": the shared address's position in this perp.
function heldTitle(mine, price) {
  const r = pnl(mine, price);
  return `Your ${mine.side} from ${fmtPx(mine.entry)}${r == null ? "" : ` · ${r >= 0 ? "+" : ""}${(100 * r).toFixed(1)}%`}`;
}

function CellContent({ colLabel, row, index, isMobile, cellPad, phone, tight, backtestSymbols, favorites, onToggleFavorite, timeframe, onSelect, folds, held }) {
  const noHistory = row.history_bars === 0;   // unmeasured, not zero
  switch (colLabel) {
    case "#":
      return (
        <td style={{ padding: cellPad, fontFamily: T.mono, fontSize: m(T.textXs, isMobile), color: T.text4, width: 28, textAlign: "center" }}>
          {index + 1}
        </td>
      );
    case "SYMBOL": {
      const isFav = favorites?.has(row.symbol);
      const base = getBaseSymbol(row.symbol);
      const priceStr = row.price
        ? formatPrice(row.price)
        : null;
      return (
        <td className="scanner-symbol" style={{ padding: cellPad, fontFamily: T.mono, fontWeight: 700, color: T.text1, fontSize: m(isMobile ? T.textMd : T.textLg, isMobile), letterSpacing: "0.02em", whiteSpace: "nowrap" }}>
          {onToggleFavorite && <button type="button" className="fav-star" aria-pressed={!!isFav}
            aria-label={`${isFav ? "Remove" : "Add"} ${base} ${isFav ? "from" : "to"} favorites`}
            title={isFav ? "Remove from favorites" : "Add to favorites"}
            onClick={e => { e.stopPropagation(); onToggleFavorite(row.symbol); }}>
            <Star size={16} strokeWidth={1.75} aria-hidden="true" {...(isFav ? { color: col("#facc15"), fill: col("#facc15") } : { fill: "none" })} />
          </button>}
          {/* A real link: a plain click opens the coin page in place; a modified click opens a new tab. */}
          <a className="scanner-ticker" href={marketHref(row, timeframe)}
            onClick={e => { if (e.button !== 0 || e.metaKey || e.ctrlKey || e.altKey) return; e.preventDefault(); e.stopPropagation(); onSelect?.(row, e); }}
            style={{ display: "inline-flex", alignItems: "center", gap: 8, verticalAlign: "middle", color: "inherit", font: "inherit", letterSpacing: "inherit", textDecoration: "none" }}>
            <TokenLogo symbol={row.symbol} size={tight ? 20 : 24} />{base}
          </a>
          {held && <span className="held-mark" role="img" aria-label={heldTitle(held, row.price)} title={heldTitle(held, row.price)} style={{ color: sideColor(held.side) }} />}
          {backtestSymbols && backtestSymbols.has(row.symbol) && (
            <span style={{ fontSize: m(T.textXs, isMobile), fontWeight: 700, color: T.green, opacity: 0.6, marginLeft: 5, letterSpacing: "0.05em" }}>BT</span>
          )}
          {priceStr && (
            <div style={{
              fontSize: 12, fontWeight: 500, letterSpacing: "0.01em", marginTop: 1,
              color: T.text1,
            }}>
              {priceStr}
              {row.sector && row.sector !== "Other" && <span title={[row.sector, row.ecosystem, row.size_tier && `${row.size_tier} size`].filter(Boolean).join(" · ")}
                style={{ color: T.text4, marginLeft: 6, fontFamily: T.font, fontWeight: 500 }}>{SECTOR_SHORT[row.sector] || row.sector}</span>}
            </div>
          )}
        </td>
      );
    }
    case "REGIME":
      return <td style={{ padding: cellPad }}><div><RegimeBadge regime={row.regime} isMobile={isMobile} noHistory={noHistory} /></div><RegimeTransition data={row} compact /></td>;
    case "SIGNAL":
      return <td style={{ padding: cellPad }}><SignalDot signal={row.signal} reason={row.signal_reason} warnings={row.signal_warnings} context={row} isMobile={isMobile} /></td>;
    case "SPARK":
      return <td style={{ padding: cellPad }} title={sparkTitle(row, timeframe, folds?.energy)}><SparklineCell data={row.sparkline} width={72} height={22} /></td>;
    case "Z-SCORE":
      return <td style={{ padding: cellPad }}>{noHistory ? DASH : <ZScoreBar z={row.zscore} isMobile={isMobile} />}</td>;
    case "ENERGY":
      return <td style={{ padding: cellPad, fontFamily: T.mono, fontSize: m(isMobile ? T.textBase : T.textMd, isMobile), color: noHistory ? T.text4 : T.text2 }}>{noHistory ? "—" : fmt(row.energy, 2)}</td>;
    case "DIV":
      return <td style={{ padding: cellPad }}><DivergencePill div={row.divergence} /></td>;
    case "HEAT":
      return <td style={{ padding: cellPad }}><HeatCell heat={row.heat} phase={row.heat_phase} exhaust={folds?.exhaust ? exhaustFold(row) : null} /></td>;
    case "EXHAUST":
      return <td style={{ padding: cellPad }}><ExhaustBadge state={row.exhaustion_state} floorConfirmed={row.floor_confirmed} /></td>;
    case "FUNDING":
      return <td style={{ padding: cellPad }}><FundingCell rate={row.positioning?.funding_rate} /></td>;
    case "SM":
      return <td style={{ padding: cellPad, textAlign: "center" }}><SmartMoneyBadge sm={row.smart_money} /></td>;
    case "OI":
      return <td style={{ padding: cellPad }}><OITrendBadge trend={row.positioning?.oi_trend} /></td>;
    case "CVD":
      return (
        <td style={{ padding: cellPad, textAlign: "center" }}>
          <CVDBadge trend={row.cvd_trend} divergence={row.cvd_divergence} bsr={row.buy_sell_ratio} isMobile={isMobile} />
        </td>
      );
    case "CONF":
      return <td className="cell-evidence" style={{ padding: cellPad }}><ConfluenceBadge score={row.confluence?.score} label={row.confluence?.label} /></td>;
    case "PRI": {
      const pri = row.priority_score ?? 0;
      // Rank reads as a bar under the number, in the accent colour only. Phones: a 2px bar.
      return (
        <td style={{ padding: cellPad }}>
          <span style={{ display: "inline-flex", flexDirection: "column", gap: phone ? 3 : 4, minWidth: 28 }}>
            <span style={{ fontFamily: T.mono, fontSize: T.textMd, fontWeight: 700, color: T.text1, letterSpacing: "0.02em" }}>
              {Math.round(pri)}
            </span>
            <span aria-hidden="true" style={{ height: phone ? 2 : 3, borderRadius: 2, background: T.overlay06, overflow: "hidden" }}>
              <span style={{ display: "block", height: "100%", width: `${Math.max(0, Math.min(100, pri))}%`, background: T.accent, opacity: 0.35 + 0.65 * Math.max(0, Math.min(1, (pri - 30) / 60)) }} />
            </span>
          </span>
        </td>
      );
    }
    case "COND": {
      const cm = row.conditions_met ?? 0;
      const ct = row.conditions_total ?? 10;
      const pct = ct > 0 ? cm / ct : 0;
      return (
        <td className="cell-evidence" style={{ padding: cellPad }}>
          <span style={{
            fontFamily: T.mono, fontSize: T.textMd, fontWeight: 700,
            color: pct >= 0.75 ? T.green : pct >= 0.5 ? T.text2 : T.text4,
          }}>
            {cm}/{ct}
          </span>
        </td>
      );
    }
    default:
      return <td style={{ padding: cellPad }}>{"—"}</td>;
  }
}

function SymbolRow({ row, index, selected, onSelect, columns, isMobile, scanner, phone, tight, line, backtestSymbols, favorites, onToggleFavorite, marketWide, timeframe, folds, held }) {
  const rm = REGIME_META[row.regime] || REGIME_META.FLAT;
  // Only locked-in rows (trend and entry signal agree) are tinted, so they stand
  // out; every other row keeps just its regime stripe on the left.
  const alignment = setupAlignment(row, { marketWide });
  const restBg = selected ? T.accentDim : "transparent";
  // Locked in: the whole regime/signal cell fills edge to edge, no inner box.
  const lockedCell = alignment.strength ? { background: `${setupColor(alignment)}${alignment.strength === 2 ? "24" : "12"}` } : {};
  // Horizontal padding follows the grid's padding tier (--cell-px); the landing keeps today's.
  const cellPad = scanner ? `${isMobile ? T.sp2 : T.sp3}px var(--cell-px,12px)` : isMobile ? `${T.sp2}px ${T.sp2}px` : `${T.sp3}px ${T.sp3}px`;
  const setupPad = scanner ? `${isMobile ? 8 : 12}px var(--cell-px,12px)` : isMobile ? 8 : 12;
  const noHistory = row.history_bars === 0;

  return (
    <tr
      data-locked={alignment.strength > 0}
      aria-selected={selected || undefined}
      tabIndex={0}
      // Controls inside the row (star, ticker link, help buttons) and portaled help cards do not open the coin.
      onClick={(e) => { if (!e.currentTarget.contains(e.target) || e.target.closest("button,a,input,summary")) return; onSelect(row, e); }}
      onKeyDown={(e) => { if (e.key === "Enter" && e.target === e.currentTarget) onSelect(row, e); }}
      style={{
        cursor: "pointer",
        borderBottom: `1px solid ${T.border}`,
        background: restBg,
        boxShadow: `inset ${alignment.strength ? 3 : 2}px 0 ${alignment.strength ? rm.color : `${rm.color}80`}`,
        transition: "background 0.2s ease",
      }}
      onMouseEnter={e => { if (!selected) e.currentTarget.style.background = T.overlay10; }}
      onMouseLeave={e => { if (!selected) e.currentTarget.style.background = restBg; }}
    >
      {columns.map(([, label], colIndex) => {
        if (label === "SIGNAL" && columns[colIndex - 1]?.[1] === "REGIME") return null;
        if (label === "REGIME" && columns[colIndex + 1]?.[1] === "SIGNAL") return <td key={label} colSpan={2} className="setup-cell" data-strength={alignment.strength} style={{padding:setupPad, ...lockedCell}}>
          <SetupPair row={row} isMobile={isMobile} transition compact marketWide={marketWide}/>
          {/* Phones, tablets and narrow windows: Z and the sparkline, when they leave the columns,
              survive compact on a second line under the pair. */}
          {line?.length > 0 && <div className="setup-phone-line">
            {line.includes("Z-SCORE") && (noHistory ? DASH : <ZScoreBar z={row.zscore} compact={tight ? 40 : true} />)}
            {line.includes("SPARK") && <span title={sparkTitle(row, timeframe, folds?.energy)}><SparklineCell data={row.sparkline} width={tight ? 48 : 56} height={16} /></span>}
          </div>}
        </td>;
        return <CellContent key={label} colLabel={label} row={row} index={index} isMobile={isMobile} phone={phone} tight={tight} cellPad={cellPad} backtestSymbols={backtestSymbols} favorites={favorites} onToggleFavorite={onToggleFavorite} timeframe={timeframe} onSelect={onSelect} folds={folds} held={held} />;
      })}
    </tr>
  );
}

const PAIR_HELP = <>
  <p>Read left to right: the regime describes the broader trend; the signal describes the current setup.</p>
  <p>A locked, outlined pair means the trend supports the entry signal; a Strong signal gets the brighter outline. A broken link marks a countertrend setup; a dashed circle means required context is missing.</p>
  <p>The highlight describes agreement, not the probability of a profitable trade.</p>
</>;

// A scanner header label: a sort button (sortable) or a help button, both with a dotted underline.
// Help opens after 600ms of resting on the label (a sweep across the header opens nothing), on
// keyboard focus, or on a 500ms touch hold; a click sorts.
// compact (phone PRI): no help, and the arrow hangs in the cell padding so the column stays narrow.
function HeaderLabel({ label, text, sortKey, active, dir, onSort, compact }) {
  const info = !compact && COLUMN_INFO[label];
  const content = <>{text}{active && <span aria-hidden="true" className={compact ? "sort-ind-hang" : undefined} style={{ color: T.accent }}>{dir === "asc" ? " \u25b2" : " \u25bc"}</span>}</>;
  const title = sortKey === "symbol" ? "Sort by market cap" : undefined;
  if (!info) {
    if (sortKey) return <button type="button" className={compact ? "table-sort table-sort-compact" : "table-sort"} title={title} onClick={() => onSort(sortKey)}>{content}</button>;
    return <span>{text}</span>;
  }
  return <HelpTip title={info.title} width={280} anchor={content} anchorClass={sortKey ? "table-sort" : "th-help"} className="th-help-wrap"
    hoverDelay={600} longPress onActivate={sortKey ? () => onSort(sortKey) : undefined} buttonProps={title ? { title } : undefined}>
    <ColumnHelp label={label} />
  </HelpTip>;
}

export default function DataTable({ results, label, sortKey, sortDir, onSort, selected, onSelect, visibleColumns, isMobile, backtestSymbols, loading, favorites, onToggleFavorite,
  variant = "embed", tf = "1d", totalCount, scopeLabel, filterWords = [], onClear }) {
  const scanner = variant === "scanner";
  // Coins the shared address holds (connected wallet or read-only view); no executor fallback.
  const { effectiveAddress } = useWallet();
  const { byCoin: heldBy } = useMyPositions(scanner ? effectiveAddress : null);
  const heldFor = row => ((row.market_kind || "perpetual") === "perpetual" ? heldBy.get(getBaseSymbol(row.symbol)) : undefined);
  const [alignedFirst, setAlignedFirst] = useState(false);
  const marketWide = useMemo(() => marketWideMissing(results), [results]);
  // The landing keeps today's rule (only with 10 or more rows); the scanner drops a column that is
  // empty on every row in view whatever the count, so a filtered view is not squeezed by dead columns.
  const shownColumns = useMemo(() => (scanner ? results.length === 0 : results.length < 10) ? visibleColumns
    : visibleColumns.filter(([, label]) => !(EMPTY_WHEN[label] && results.every(EMPTY_WHEN[label]))), [visibleColumns, results, scanner]);
  const displayedResults = alignedFirst ? [...results].sort((a,b) => setupAlignment(b, { marketWide }).strength - setupAlignment(a, { marketWide }).strength) : results;

  // ── Fit (scanner only): which columns fit the grid's own width, at which padding tier ──
  const wrapRef = useRef(null);
  const tableRef = useRef(null);
  const W = useElementWidth(scanner ? wrapRef : NO_REF);
  const candidateKey = shownColumns.map(([, l]) => l).join("|");
  const [fontsReady, setFontsReady] = useState(0);
  useEffect(() => {
    if (!scanner || !document.fonts?.ready) return undefined;
    let live = true;
    document.fonts.ready.then(() => { if (live) setFontsReady(n => n + 1); });
    return () => { live = false; };
  }, [scanner]);
  // Safety net: columns dropped beyond the computed fit when the table still overflows after paint.
  const [extraDrops, setExtraDrops] = useState(0);
  const [overflowing, setOverflowing] = useState(false);
  const dropBase = useRef({ key: candidateKey, w: W, fonts: fontsReady });
  useLayoutEffect(() => {
    const base = dropBase.current;
    if (base.key !== candidateKey || base.fonts !== fontsReady || (W != null && base.w != null && W - base.w >= 40)) {
      dropBase.current = { key: candidateKey, w: W, fonts: fontsReady };
      setExtraDrops(0); setOverflowing(false);
    } else if (W != null && (base.w == null || W < base.w)) base.w = W;
  }, [candidateKey, W, fontsReady]);
  const fit = useMemo(() => (scanner && W ? fitColumns(candidateKey ? candidateKey.split("|") : [], W, { extraDrops }) : null),
    [scanner, W, candidateKey, extraDrops, fontsReady]); // eslint-disable-line react-hooks/exhaustive-deps
  const columns = fit ? shownColumns.filter(([, l]) => fit.visible.includes(l)) : shownColumns;
  const caps = fit && !fit.phone ? widthCaps(fit.visible, W, fit.pad) : null;
  const phone = !!fit?.phone;
  const tight = !!fit?.tight;
  const line = fit?.line;
  const folds = fit ? { energy: fit.hidden.includes("ENERGY"), exhaust: fit.hidden.includes("EXHAUST") } : null;
  useLayoutEffect(() => {
    if (!fit) return;
    const wrap = wrapRef.current, table = tableRef.current;
    if (!wrap || !table) return;
    const over = Math.max(table.scrollWidth, table.offsetWidth) > wrap.clientWidth + 1;
    if (over && extraDrops < 3) setExtraDrops(n => n + 1);
    else setOverflowing(over);
  }, [fit, results, extraDrops]);
  const fits = scanner && !overflowing;
  // Stuck header: once the table scrolls under the capsule, the header's top corners square off
  // so no row shows through beside them. Written straight to the DOM; no re-render while scrolling.
  useEffect(() => {
    const wrap = wrapRef.current, table = tableRef.current;
    if (!fits || !wrap || !table) return undefined;
    let frame = 0;
    const check = () => {
      frame = 0;
      const cell = table.tHead?.rows[0]?.cells[0];   // the cells stick, not the thead box
      if (!cell) return;
      const stuck = cell.getBoundingClientRect().top - table.getBoundingClientRect().top > 1;
      if (stuck !== wrap.hasAttribute("data-stuck")) wrap.toggleAttribute("data-stuck", stuck);
    };
    const onScroll = () => { if (!frame) frame = requestAnimationFrame(check); };
    check();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => { cancelAnimationFrame(frame); window.removeEventListener("scroll", onScroll); window.removeEventListener("resize", onScroll); wrap.removeAttribute("data-stuck"); };
  }, [fits]);

  // Column guide: the columns hidden to fit (Z and the sparkline on the line under the pair are not hidden), then every legend.
  const hiddenLabels = fit && results.length ? fit.hidden.filter(l => !fit.line.includes(l)) : [];
  const guideLabels = shownColumns.map(([, l]) => l).filter(l => COLUMN_INFO[l]);
  const filtered = filterWords.length > 0;

  const thColor = key => (key && sortKey === key ? T.accent : T.text3);
  const renderHead = () => columns.map(([key0, colLabel], colIndex) => {
    if (colLabel === 'SIGNAL' && columns[colIndex-1]?.[1] === 'REGIME') return null;
    const paired = colLabel === 'REGIME' && columns[colIndex+1]?.[1] === 'SIGNAL';
    if (!scanner) {
      const key = key0;
      return (
        <th colSpan={paired ? 2 : 1} className={colLabel === "SYMBOL" ? "scanner-symbol" : undefined}
          key={colLabel}
          onClick={() => key && onSort(key)}
          style={{
            padding: isMobile ? `${T.sp2 + 2}px ${T.sp2 + 2}px` : `${T.sp3}px ${T.sp3}px`,
            textAlign: colLabel === "CVD" ? "center" : "left",
            fontFamily: T.font, fontSize: m(isMobile ? T.textSm : T.textBase, isMobile), fontWeight: 700,
            color: thColor(key),
            letterSpacing: "0.08em", cursor: key ? "pointer" : "default",
            userSelect: "none", whiteSpace: "nowrap",
            textTransform: "uppercase",
            transition: "color 0.2s",
            borderBottom: `2px solid ${T.border}`,
          }}
        >
          <span style={{ display: "inline-flex", alignItems: "center" }}>
            {paired ? <span className="setup-pair-head"><span>Regime</span><span aria-hidden="true" /><span>Signal</span></span> : colLabel}{key && sortKey === key ? " ▼" : ""}
            {paired ? <HelpTip title="Structure meets signal" width={320}>{PAIR_HELP}</HelpTip> : colLabel !== "SYMBOL" && colLabel !== "SPARK" && colLabel !== "PRICE" && <InfoButton label={colLabel} />}
          </span>
        </th>
      );
    }
    const key = key0 || COLUMN_FIT[colLabel]?.sort || null;
    const active = !!key && sortKey === key;
    return (
      <th colSpan={paired ? 2 : 1} className={colLabel === "SYMBOL" ? "scanner-symbol" : undefined} key={colLabel}
        aria-sort={key ? (active ? (sortDir === "asc" ? "ascending" : "descending") : "none") : undefined}
        style={{
          padding: `${isMobile ? T.sp2 : T.sp3}px var(--cell-px,12px)`,
          textAlign: colLabel === "CVD" ? "center" : "left",
          fontFamily: T.font, fontSize: m(isMobile ? T.textSm : T.textBase, isMobile), fontWeight: 700,
          color: thColor(key), letterSpacing: "0.02em",
          userSelect: "none", whiteSpace: "nowrap", textTransform: "uppercase",
          transition: "color 0.2s", borderBottom: `2px solid ${T.border}`,
        }}>
        <span style={{ display: "inline-flex", alignItems: "center" }}>
          {paired
            ? <span className="setup-pair-head">
                <HeaderLabel label="REGIME" text="Regime" sortKey={key} active={active} dir={sortDir} onSort={onSort} />
                <span aria-hidden="true" />
                <HeaderLabel label="SIGNAL" text="Signal" />
              </span>
            : <HeaderLabel label={colLabel} text={colLabel} sortKey={key} active={active} dir={sortDir} onSort={onSort} compact={phone && colLabel === "PRI"} />}
          {paired && <HelpTip title="Structure meets signal" width={320}>{PAIR_HELP}</HelpTip>}
        </span>
      </th>
    );
  });

  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      {label && (
        <div style={{
          fontFamily: T.font, fontSize: m(T.textSm, isMobile), color: T.text3, fontWeight: 700,
          letterSpacing: "0.12em", marginBottom: T.sp3, paddingLeft: isMobile ? T.sp3 : T.sp4,
          textTransform: "uppercase",
        }}>{label}</div>
      )}
      {!scanner && <div style={{display:'flex',justifyContent:'flex-end',marginBottom:8}}><button type="button" aria-pressed={alignedFirst} onClick={()=>setAlignedFirst(v=>!v)} title={ALIGNED_TITLE} style={{background:alignedFirst ? T.accentDim : 'transparent',color:alignedFirst ? T.accent : T.text3,border:`1px solid ${T.border}`,borderRadius:6,padding:'6px 10px',fontSize:12,cursor:'pointer'}}>Aligned setups first</button></div>}
      {marketWide.length > 0 && <p role="status" style={{margin: scanner ? "16px 0 0" : "0 0 10px",padding:"10px 14px",border:`1px solid ${T.border}`,borderRadius:8,fontSize:12,lineHeight:1.6,color:T.text2}}>
        Market-wide input unavailable: {marketWide.join(", ")}. Strong Long cannot be confirmed on any market until it returns; other signals are unaffected.
      </p>}
      {scanner && (
        <div className="grid-toolbar" style={marketWide.length > 0 ? { marginTop: 8 } : undefined}>
          <div className="grid-toolbar-count">
            {totalCount > 0 && (filtered
              ? <><span className="grid-toolbar-num">{results.length}</span> of <span className="grid-toolbar-num">{totalCount}</span>
                  {filterWords.map((w, i) => <span key={i}><span className="grid-toolbar-sep"> · </span><span style={{ color: w.color }}>{w.text}</span></span>)}</>
              : <><span className="grid-toolbar-num">{totalCount}</span> {scopeLabel}</>)}
            {filtered && onClear && <button type="button" className="te-link grid-toolbar-clear" onClick={onClear}>Clear</button>}
          </div>
          <div className="grid-toolbar-actions">
            <button type="button" className="te-toggle grid-aligned" aria-pressed={alignedFirst} onClick={() => setAlignedFirst(v => !v)} title={ALIGNED_TITLE}>
              <svg className="grid-aligned-box" width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
                <rect x="1" y="1" width="10" height="10" rx="2" />
                {alignedFirst && <path d="M3.4 6.2l1.8 1.8 3.5-3.8" />}
              </svg>
              <span>Aligned setups first</span>
            </button>
            <HelpTip trigger="click" width={420} title="Column guide" className="grid-guide" anchorClass="te-toggle"
              anchor={<>Column guide{hiddenLabels.length ? <span className="grid-guide-count"> · {hiddenLabels.length} hidden</span> : null}</>}>
              {hiddenLabels.length > 0 && <p className="grid-guide-hidden">Hidden to fit this window: {hiddenLabels.map(l => SHORT_NAME[l] || l).join(", ")}. Every value is on the coin page.</p>}
              <div className="grid-guide-col"><strong>Structure meets signal</strong>{PAIR_HELP}</div>
              {guideLabels.map(l => <div key={l} className="grid-guide-col"><strong>{COLUMN_INFO[l].title}</strong><ColumnHelp label={l} /></div>)}
            </HelpTip>
          </div>
        </div>
      )}
      <GlassCard className="terminal-data-table" style={{ overflow: "visible" }}>
        <div ref={wrapRef} className={fits ? "grid-fits" : undefined} style={{ overflowX: scanner ? (fits ? "clip" : "auto") : "auto", WebkitOverflowScrolling: "touch" }}>
          <table ref={tableRef} className={phone ? (tight ? "grid-phone grid-tight" : "grid-phone") : line?.length ? "grid-folded" : undefined} style={{ width: "100%", borderCollapse: "collapse", ...(fit ? { "--cell-px": `${fit.pad}px` } : null) }}>
            {caps && <colgroup>{columns.map(([, l]) => <col key={l} style={caps[l] ? { width: caps[l] } : undefined} />)}</colgroup>}
            <thead>
              <tr style={{ borderBottom: `1px solid ${T.borderH}` }}>
                {renderHead()}
              </tr>
            </thead>
            <tbody>
              {loading && results.length === 0 ? (
                <tr><td colSpan={columns.length} style={{ padding: 0 }}>
                  <TableSkeleton rows={12} cols={Math.min(columns.length, 8)} />
                </td></tr>
              ) : results.length === 0 ? (
                <tr><td colSpan={columns.length} style={{
                  padding: "60px 14px", textAlign: "center",
                  color: T.text3, fontFamily: T.font, fontSize: T.textBase,
                }}>
                  No markets match this view. Clear the search or filters to broaden it.
                </td></tr>
              ) : (
                displayedResults.map((row, idx) => (
                  <SymbolRow
                    key={row.symbol}
                    row={row}
                    index={idx}
                    held={heldFor(row)}
                    selected={selected?.symbol === row.symbol}
                    onSelect={onSelect}
                    columns={columns}
                    marketWide={marketWide}
                    isMobile={isMobile}
                    scanner={scanner}
                    phone={phone}
                    tight={tight}
                    line={line}
                    backtestSymbols={backtestSymbols}
                    favorites={favorites}
                    onToggleFavorite={onToggleFavorite}
                    timeframe={tf}
                    folds={folds}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      </GlassCard>
    </div>
  );
}
