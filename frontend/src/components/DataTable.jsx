import HelpTip from "./HelpTip.jsx";
import { useMemo, useState } from "react";
import { setupAlignment, marketWideMissing } from "../utils/signalPresentation.js";
import { SECTOR_SHORT } from "../utils/sectors.js";
import SetupPair, { setupColor } from "./SetupPair.jsx";
import TokenLogo from "./TokenLogo.jsx";
import RegimeTransition from "./RegimeTransition.jsx";
import { T, m, REGIME_META, fmt, getBaseSymbol } from "../theme.js";
import { TableSkeleton } from "./Skeleton.jsx";
import {
  ZScoreBar, RegimeBadge, SignalDot, DivergencePill,
  HeatCell, PhaseCell, ExhaustBadge, FloorCell,
  FundingCell, OITrendBadge, ConfluenceBadge, CVDBadge,
  SmartMoneyBadge,
} from "./badges.jsx";
import SparklineCell from "./SparklineCell.jsx";
import InfoButton from "./InfoPopover.jsx";
import GlassCard from "./GlassCard.jsx";

// Optional columns hidden while every row in view would show only a dash, so the
// grid carries no dead columns (e.g. no divergences or exhaustion states today).
const EMPTY_WHEN = {
  DIV: r => !r.divergence,
  EXHAUST: r => !r.exhaustion_state || r.exhaustion_state === "NEUTRAL",
  SM: r => !r.smart_money?.trend || r.smart_money.trend === "NEUTRAL",
  OI: r => !r.positioning?.oi_trend,
  CVD: r => !r.cvd_trend || ["NEUTRAL", "UNAVAILABLE"].includes(r.cvd_trend),
};

function CellContent({ colLabel, row, index, isMobile, backtestSymbols, favorites, onToggleFavorite, priceFlash }) {
  const cellPad = isMobile ? `${T.sp2}px ${T.sp2}px` : `${T.sp3}px ${T.sp3}px`;
  switch (colLabel) {
    case "#":
      return (
        <td style={{ padding: cellPad, fontFamily: T.mono, fontSize: m(T.textXs, isMobile), color: T.text4, width: 28, textAlign: "center" }}>
          {index + 1}
        </td>
      );
    case "SYMBOL": {
      const flash = priceFlash?.get?.(row.symbol);
      const isFav = favorites?.has(row.symbol);
      const priceStr = row.price
        ? (row.price < 1 ? `$${fmt(row.price, 5)}` : `$${fmt(row.price, 2)}`)
        : null;
      return (
        <td className="scanner-symbol" style={{ padding: cellPad, fontFamily: T.mono, fontWeight: 700, color: T.text1, fontSize: m(isMobile ? T.textMd : T.textLg, isMobile), letterSpacing: "0.02em", whiteSpace: "nowrap" }}>
          <span
            onClick={e => { e.stopPropagation(); onToggleFavorite?.(row.symbol); }}
            style={{ cursor: "pointer", marginRight: 6, fontSize: isMobile ? 20 : 22, color: isFav ? "#facc15" : T.text4, transition: "color 0.15s", lineHeight: 1, verticalAlign: "middle" }}
            title={isFav ? "Remove from favorites" : "Add to favorites"}
          >{isFav ? "\u2605" : "\u2606"}</span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 8, verticalAlign: "middle" }}><TokenLogo symbol={row.symbol} />{getBaseSymbol(row.symbol)}</span>
          {backtestSymbols && backtestSymbols.has(row.symbol) && (
            <span style={{ fontSize: m(T.textXs, isMobile), fontWeight: 700, color: T.green, opacity: 0.6, marginLeft: 5, letterSpacing: "0.05em" }}>BT</span>
          )}
          {priceStr && (
            <div style={{
              fontSize: isMobile ? 10 : 11, fontWeight: 500, letterSpacing: "0.01em", marginTop: 1,
              color: flash === "up" ? T.green : flash === "down" ? T.red : T.text1,
              transition: "color 0.3s ease",
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
      return <td style={{ padding: cellPad }}><div><RegimeBadge regime={row.regime} isMobile={isMobile} /></div><RegimeTransition data={row} compact /></td>;
    case "SIGNAL":
      return <td style={{ padding: cellPad }}><SignalDot signal={row.signal} reason={row.signal_reason} warnings={row.signal_warnings} context={row} isMobile={isMobile} /></td>;
    case "SPARK":
      return <td style={{ padding: cellPad }}><SparklineCell data={row.sparkline} width={72} height={22} /></td>;
    case "Z-SCORE":
      return <td style={{ padding: cellPad }}><ZScoreBar z={row.zscore} isMobile={isMobile} /></td>;
    case "ENERGY":
      return <td style={{ padding: cellPad, fontFamily: T.mono, fontSize: m(isMobile ? T.textBase : T.textMd, isMobile), color: T.text2 }}>{fmt(row.energy, 2)}</td>;
    case "MOM":
      return (
        <td style={{ padding: cellPad, fontFamily: T.mono, fontSize: m(isMobile ? T.textBase : T.textMd, isMobile) }}>
          <span style={{ color: row.momentum >= 0 ? T.green : T.red, fontWeight: 600 }}>
            {row.momentum != null ? `${row.momentum >= 0 ? "+" : ""}${fmt(row.momentum, 1)}%` : "\u2014"}
          </span>
        </td>
      );
    case "DIV":
      return <td style={{ padding: cellPad }}><DivergencePill div={row.divergence} /></td>;
    case "PRICE": {
      const pFlash = priceFlash?.get?.(row.symbol);
      return (
        <td style={{
          padding: cellPad, fontFamily: T.mono, fontSize: m(isMobile ? T.textBase : T.textMd, isMobile), fontWeight: 500,
          color: pFlash === "up" ? T.green : pFlash === "down" ? T.red : T.text1,
          transition: "color 0.3s ease",
        }}>
          {row.price ? `$${row.price < 1 ? fmt(row.price, 5) : fmt(row.price, 2)}` : "\u2014"}
        </td>
      );
    }
    case "HEAT":
      return <td style={{ padding: cellPad }}><HeatCell heat={row.heat} phase={row.heat_phase} /></td>;
    case "PHASE":
      return <td style={{ padding: cellPad }}><PhaseCell phase={row.heat_phase} /></td>;
    case "EXHAUST":
      return <td style={{ padding: cellPad }}><ExhaustBadge state={row.exhaustion_state} floorConfirmed={row.floor_confirmed} /></td>;
    case "FLOOR":
    case "FORMING":
      return <td style={{ padding: cellPad }}><FloorCell confirmed={row.floor_confirmed} /></td>;
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
      // Rank reads as a bar under the number, in the accent colour only.
      return (
        <td style={{ padding: cellPad }}>
          <span style={{ display: "inline-flex", flexDirection: "column", gap: 4, minWidth: 28 }}>
            <span style={{ fontFamily: T.mono, fontSize: T.textMd, fontWeight: 700, color: T.text1, letterSpacing: "0.02em" }}>
              {Math.round(pri)}
            </span>
            <span aria-hidden="true" style={{ height: 3, borderRadius: 2, background: T.overlay06, overflow: "hidden" }}>
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
      return <td style={{ padding: cellPad }}>{"\u2014"}</td>;
  }
}

function SymbolRow({ row, index, selected, onSelect, visibleColumns, isMobile, backtestSymbols, favorites, onToggleFavorite, priceFlash, marketWide }) {
  const rm = REGIME_META[row.regime] || REGIME_META.FLAT;
  // Only locked-in rows (trend and entry signal agree) are tinted, so they stand
  // out; every other row keeps just its regime stripe on the left.
  const alignment = setupAlignment(row, { marketWide });
  const restBg = selected ? T.accentDim : "transparent";
  // Locked in: the whole regime/signal cell fills edge to edge, no inner box.
  const lockedCell = alignment.strength ? { background: `${setupColor(alignment)}${alignment.strength === 2 ? "24" : "12"}` } : {};

  return (
    <tr
      data-locked={alignment.strength > 0}
      onClick={(e) => onSelect(row, e)}
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
      {visibleColumns.map(([, label], colIndex) => {
        if (label === "SIGNAL" && visibleColumns[colIndex - 1]?.[1] === "REGIME") return null;
        if (label === "REGIME" && visibleColumns[colIndex + 1]?.[1] === "SIGNAL") return <td key={label} colSpan={2} className="setup-cell" data-strength={alignment.strength} style={{padding:isMobile ? 8 : 12, ...lockedCell}}><SetupPair row={row} isMobile={isMobile} transition compact marketWide={marketWide}/></td>;
        return <CellContent key={label} colLabel={label} row={row} index={index} isMobile={isMobile} backtestSymbols={backtestSymbols} favorites={favorites} onToggleFavorite={onToggleFavorite} priceFlash={priceFlash} />;
      })}
    </tr>
  );
}

export default function DataTable({ results, label, sortKey, onSort, selected, onSelect, visibleColumns, isMobile, backtestSymbols, loading, favorites, onToggleFavorite, priceFlash }) {
  const [alignedFirst, setAlignedFirst] = useState(false);
  const marketWide = useMemo(() => marketWideMissing(results), [results]);
  const shownColumns = useMemo(() => results.length < 10 ? visibleColumns : visibleColumns.filter(([, label]) => !(EMPTY_WHEN[label] && results.every(EMPTY_WHEN[label]))), [visibleColumns, results]);
  const displayedResults = alignedFirst ? [...results].sort((a,b) => setupAlignment(b, { marketWide }).strength - setupAlignment(a, { marketWide }).strength) : results;
  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      {label && (
        <div style={{
          fontFamily: T.font, fontSize: m(T.textSm, isMobile), color: T.text3, fontWeight: 700,
          letterSpacing: "0.12em", marginBottom: T.sp3, paddingLeft: isMobile ? T.sp3 : T.sp4,
          textTransform: "uppercase",
        }}>{label}</div>
      )}
      <div style={{display:'flex',justifyContent:'flex-end',marginBottom:8}}><button type="button" aria-pressed={alignedFirst} onClick={()=>setAlignedFirst(v=>!v)} title="Group aligned regime and signal setups first, preserving the selected order within each strength. Does not change engine scores." style={{background:alignedFirst ? T.accentDim : 'transparent',color:alignedFirst ? T.accent : T.text3,border:`1px solid ${T.border}`,borderRadius:6,padding:'6px 10px',fontSize:11,cursor:'pointer'}}>Aligned setups first</button></div>
      {marketWide.length > 0 && <p role="status" style={{margin:"0 0 10px",padding:"10px 14px",border:`1px solid ${T.border}`,borderRadius:8,fontSize:12,lineHeight:1.6,color:T.text2}}>
        Market-wide input unavailable: {marketWide.join(", ")}. Strong Long cannot be confirmed on any market until it returns; other signals are unaffected.
      </p>}
      <GlassCard className="terminal-data-table" style={{ overflow: "visible" }}>
        <div style={{ overflowX: "auto", WebkitOverflowScrolling: "touch" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${T.borderH}` }}>
                {shownColumns.map(([key, colLabel], colIndex) => {
                  if (colLabel === 'SIGNAL' && shownColumns[colIndex-1]?.[1] === 'REGIME') return null;
                  const paired = colLabel === 'REGIME' && shownColumns[colIndex+1]?.[1] === 'SIGNAL';
                  return (
                  <th colSpan={paired ? 2 : 1} className={colLabel === "SYMBOL" ? "scanner-symbol" : undefined}
                    key={colLabel}
                    onClick={() => key && onSort(key)}
                    style={{
                      padding: isMobile ? `${T.sp2 + 2}px ${T.sp2 + 2}px` : `${T.sp3}px ${T.sp3}px`,
                      textAlign: colLabel === "CVD" ? "center" : "left",
                      fontFamily: T.font, fontSize: m(isMobile ? T.textSm : T.textBase, isMobile), fontWeight: 700,
                      color: sortKey === key ? T.accent : T.text3,
                      letterSpacing: "0.08em", cursor: key ? "pointer" : "default",
                      userSelect: "none", whiteSpace: "nowrap",
                      textTransform: "uppercase",
                      transition: "color 0.2s",
                      borderBottom: `2px solid ${T.border}`,
                    }}
                  >
                    <span style={{ display: "inline-flex", alignItems: "center" }}>
                      {paired ? <span className="setup-pair-head"><span>Regime</span><span aria-hidden="true" /><span>Signal</span></span> : colLabel}{key && sortKey === key ? " \u25bc" : ""}
                      {paired ? <HelpTip title="Structure meets signal" width={320}><p>Read left to right: the regime describes the broader trend; the signal describes the current setup.</p><p>A locked, outlined pair means the trend supports the entry signal; a Strong signal gets the brighter outline. A broken link marks a countertrend setup; a dashed circle means required context is missing.</p><p>The highlight It describes agreement, not the probability of a profitable trade.</p></HelpTip> : colLabel !== "SYMBOL" && colLabel !== "SPARK" && colLabel !== "PRICE" && <InfoButton label={colLabel} />}
                    </span>
                  </th>
                );})}
              </tr>
            </thead>
            <tbody>
              {loading && results.length === 0 ? (
                <tr><td colSpan={visibleColumns.length} style={{ padding: 0 }}>
                  <TableSkeleton rows={12} cols={Math.min(visibleColumns.length, 8)} />
                </td></tr>
              ) : results.length === 0 ? (
                <tr><td colSpan={visibleColumns.length} style={{
                  padding: "60px 14px", textAlign: "center",
                  color: T.text4, fontFamily: T.mono, fontSize: T.textBase,
                }}>
                  NO DATA
                </td></tr>
              ) : (
                displayedResults.map((row, idx) => (
                  <SymbolRow
                    key={row.symbol}
                    row={row}
                    index={idx}
                    selected={selected?.symbol === row.symbol}
                    onSelect={onSelect}
                    visibleColumns={shownColumns}
                    marketWide={marketWide}
                    isMobile={isMobile}
                    backtestSymbols={backtestSymbols}
                    favorites={favorites}
                    onToggleFavorite={onToggleFavorite}
                    priceFlash={priceFlash}
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
