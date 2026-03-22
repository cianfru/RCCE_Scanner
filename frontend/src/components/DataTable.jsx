import { T, m, REGIME_META, fmt, getBaseSymbol } from "../theme.js";
import {
  ZScoreBar, RegimeBadge, SignalDot, DivergencePill,
  HeatCell, PhaseCell, ExhaustBadge, FloorCell,
  FundingCell, OITrendBadge, ConfluenceBadge, CVDBadge,
} from "./badges.jsx";
import SparklineCell from "./SparklineCell.jsx";
import InfoButton from "./InfoPopover.jsx";
import GlassCard from "./GlassCard.jsx";

function CellContent({ colLabel, row, index, isMobile, backtestSymbols, favorites, onToggleFavorite }) {
  const cellPad = isMobile ? `${T.sp2}px ${T.sp2}px` : `${T.sp3}px ${T.sp3}px`;
  switch (colLabel) {
    case "#":
      return (
        <td style={{ padding: cellPad, fontFamily: T.mono, fontSize: m(T.textXs, isMobile), color: T.text4, width: 28, textAlign: "center" }}>
          {index + 1}
        </td>
      );
    case "SYMBOL": {
      const isFav = favorites?.has(row.symbol);
      const priceStr = row.price
        ? (row.price < 1 ? `$${fmt(row.price, 5)}` : `$${fmt(row.price, 2)}`)
        : null;
      return (
        <td style={{ padding: cellPad, fontFamily: T.mono, fontWeight: 700, color: T.text1, fontSize: m(isMobile ? T.textMd : T.textLg, isMobile), letterSpacing: "0.02em", whiteSpace: "nowrap" }}>
          <span
            onClick={e => { e.stopPropagation(); onToggleFavorite?.(row.symbol); }}
            style={{ cursor: "pointer", marginRight: 6, fontSize: isMobile ? 14 : 16, color: isFav ? "#facc15" : T.text4, transition: "color 0.15s", lineHeight: 1, verticalAlign: "middle" }}
            title={isFav ? "Remove from favorites" : "Add to favorites"}
          >{isFav ? "\u2605" : "\u2606"}</span>
          <span style={{ verticalAlign: "middle" }}>{getBaseSymbol(row.symbol)}</span>
          {backtestSymbols && backtestSymbols.has(row.symbol) && (
            <span style={{ fontSize: m(T.textXs, isMobile), fontWeight: 700, color: T.green, opacity: 0.6, marginLeft: 5, letterSpacing: "0.05em" }}>BT</span>
          )}
          {priceStr && (
            <div style={{ fontSize: isMobile ? 10 : 11, fontWeight: 500, color: T.text1, letterSpacing: "0.01em", marginTop: 1 }}>
              {priceStr}
            </div>
          )}
        </td>
      );
    }
    case "REGIME":
      return <td style={{ padding: cellPad }}><RegimeBadge regime={row.regime} isMobile={isMobile} /></td>;
    case "SIGNAL":
      return <td style={{ padding: cellPad }}><SignalDot signal={row.signal} reason={row.signal_reason} warnings={row.signal_warnings} isMobile={isMobile} /></td>;
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
    case "PRICE":
      return (
        <td style={{ padding: cellPad, fontFamily: T.mono, fontSize: m(isMobile ? T.textBase : T.textMd, isMobile), color: T.text1, fontWeight: 500 }}>
          {row.price ? `$${row.price < 1 ? fmt(row.price, 5) : fmt(row.price, 2)}` : "\u2014"}
        </td>
      );
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
    case "OI":
      return <td style={{ padding: cellPad }}><OITrendBadge trend={row.positioning?.oi_trend} /></td>;
    case "CVD":
      return (
        <td style={{ padding: cellPad, textAlign: "center" }}>
          <CVDBadge trend={row.cvd_trend} divergence={row.cvd_divergence} bsr={row.buy_sell_ratio} isMobile={isMobile} />
        </td>
      );
    case "CONF":
      return <td style={{ padding: cellPad }}><ConfluenceBadge score={row.confluence?.score} label={row.confluence?.label} /></td>;
    case "PRI": {
      const pri = row.priority_score ?? 0;
      const priColor = pri >= 75 ? T.green : pri >= 50 ? T.cyan : pri >= 30 ? T.yellow : T.text4;
      return (
        <td style={{ padding: cellPad }}>
          <span style={{
            fontFamily: T.mono, fontSize: T.textMd, fontWeight: 700,
            color: priColor, letterSpacing: "0.02em",
          }}>
            {Math.round(pri)}
          </span>
        </td>
      );
    }
    case "COND": {
      const cm = row.conditions_met ?? 0;
      const ct = row.conditions_total ?? 10;
      const pct = ct > 0 ? cm / ct : 0;
      return (
        <td style={{ padding: cellPad }}>
          <span style={{
            fontFamily: T.mono, fontSize: T.textMd, fontWeight: 700,
            color: pct >= 0.75 ? T.green : pct >= 0.5 ? T.yellow : T.text4,
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

function SymbolRow({ row, index, selected, onSelect, visibleColumns, isMobile, backtestSymbols, favorites, onToggleFavorite }) {
  const rm = REGIME_META[row.regime] || REGIME_META.FLAT;
  const isHighlight = ["STRONG_LONG", "LIGHT_LONG", "TRIM_HARD", "RISK_OFF"].includes(row.signal);
  const stripeBg = index % 2 === 1 ? T.overlay02 : "transparent";
  const restBg = selected ? "rgba(34,211,238,0.04)" : isHighlight ? rm.bg : stripeBg;

  return (
    <tr
      onClick={() => onSelect(row)}
      style={{
        cursor: "pointer",
        borderBottom: `1px solid ${T.border}`,
        background: restBg,
        transition: "background 0.2s ease",
      }}
      onMouseEnter={e => { if (!selected) e.currentTarget.style.background = T.overlay10; }}
      onMouseLeave={e => { if (!selected) e.currentTarget.style.background = restBg; }}
    >
      {visibleColumns.map(([, label]) => (
        <CellContent key={label} colLabel={label} row={row} index={index} isMobile={isMobile} backtestSymbols={backtestSymbols} favorites={favorites} onToggleFavorite={onToggleFavorite} />
      ))}
    </tr>
  );
}

export default function DataTable({ results, label, sortKey, onSort, selected, onSelect, visibleColumns, isMobile, backtestSymbols, loading, favorites, onToggleFavorite }) {
  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      {label && (
        <div style={{
          fontFamily: T.font, fontSize: m(T.textSm, isMobile), color: T.text3, fontWeight: 700,
          letterSpacing: "0.12em", marginBottom: T.sp3, paddingLeft: isMobile ? T.sp3 : T.sp4,
          textTransform: "uppercase",
        }}>{label}</div>
      )}
      <GlassCard style={{ overflow: "visible" }}>
        <div style={{ overflowX: "auto", WebkitOverflowScrolling: "touch" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${T.borderH}` }}>
                {visibleColumns.map(([key, colLabel]) => (
                  <th
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
                      {colLabel}{key && sortKey === key ? " \u25bc" : ""}
                      {colLabel !== "SYMBOL" && colLabel !== "SPARK" && colLabel !== "PRICE" && <InfoButton label={colLabel} />}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {results.length === 0 ? (
                <tr><td colSpan={visibleColumns.length} style={{
                  padding: "60px 14px", textAlign: "center",
                  color: T.text4, fontFamily: T.mono, fontSize: T.textBase,
                }}>
                  {loading ? (
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                      <span style={{ animation: "spin 1.5s linear infinite", display: "inline-block" }}>{"\u25e0"}</span>
                      LOADING...
                    </span>
                  ) : "NO DATA"}
                </td></tr>
              ) : (
                results.map((row, idx) => (
                  <SymbolRow
                    key={row.symbol}
                    row={row}
                    index={idx}
                    selected={selected?.symbol === row.symbol}
                    onSelect={onSelect}
                    visibleColumns={visibleColumns}
                    isMobile={isMobile}
                    backtestSymbols={backtestSymbols}
                    favorites={favorites}
                    onToggleFavorite={onToggleFavorite}
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
