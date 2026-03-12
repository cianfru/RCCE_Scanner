import { T, REGIME_META, fmt, getBaseSymbol } from "../theme.js";
import {
  ZScoreBar, RegimeBadge, SignalDot, DivergencePill,
  HeatCell, PhaseCell, ExhaustBadge, FloorCell,
  FundingCell, OITrendBadge, ConfluenceBadge,
} from "./badges.jsx";
import SparklineCell from "./SparklineCell.jsx";
import InfoButton from "./InfoPopover.jsx";
import GlassCard from "./GlassCard.jsx";

function CellContent({ colLabel, row, isMobile, backtestSymbols }) {
  const cellPad = isMobile ? "10px 8px" : "12px 10px";
  switch (colLabel) {
    case "SYMBOL":
      return (
        <td style={{ padding: isMobile ? "10px 8px" : "12px 10px", fontFamily: T.mono, fontWeight: 700, color: T.text1, fontSize: isMobile ? 13 : 14, letterSpacing: "0.02em" }}>
          {getBaseSymbol(row.symbol)}
          {backtestSymbols && backtestSymbols.has(row.symbol) && (
            <span style={{ fontSize: 9, fontWeight: 700, color: "#34d399", opacity: 0.6, marginLeft: 5, letterSpacing: "0.05em" }}>BT</span>
          )}
        </td>
      );
    case "REGIME":
      return <td style={{ padding: cellPad }}><RegimeBadge regime={row.regime} /></td>;
    case "SIGNAL":
      return <td style={{ padding: cellPad }}><SignalDot signal={row.signal} reason={row.signal_reason} warnings={row.signal_warnings} isMobile={isMobile} /></td>;
    case "SPARK":
      return <td style={{ padding: cellPad }}><SparklineCell data={row.sparkline} width={56} height={22} /></td>;
    case "Z-SCORE":
      return <td style={{ padding: cellPad }}><ZScoreBar z={row.zscore} isMobile={isMobile} /></td>;
    case "ENERGY":
      return <td style={{ padding: cellPad, fontFamily: T.mono, fontSize: isMobile ? 12 : 13, color: T.text2 }}>{fmt(row.energy, 2)}</td>;
    case "MOM":
      return (
        <td style={{ padding: cellPad, fontFamily: T.mono, fontSize: isMobile ? 12 : 13 }}>
          <span style={{ color: row.momentum >= 0 ? "#34d399" : "#f87171", fontWeight: 600 }}>
            {row.momentum != null ? `${row.momentum >= 0 ? "+" : ""}${fmt(row.momentum, 1)}%` : "\u2014"}
          </span>
        </td>
      );
    case "DIV":
      return <td style={{ padding: cellPad }}><DivergencePill div={row.divergence} /></td>;
    case "PRICE":
      return (
        <td style={{ padding: cellPad, fontFamily: T.mono, fontSize: isMobile ? 12 : 13, color: T.text1, fontWeight: 500 }}>
          {row.price ? `$${row.price < 1 ? fmt(row.price, 5) : fmt(row.price, 2)}` : "\u2014"}
        </td>
      );
    case "HEAT":
      return <td style={{ padding: cellPad }}><HeatCell heat={row.heat} /></td>;
    case "PHASE":
      return <td style={{ padding: cellPad }}><PhaseCell phase={row.heat_phase} /></td>;
    case "EXHAUST":
      return <td style={{ padding: cellPad }}><ExhaustBadge state={row.exhaustion_state} /></td>;
    case "FLOOR":
      return <td style={{ padding: cellPad }}><FloorCell confirmed={row.floor_confirmed} /></td>;
    case "FUNDING":
      return <td style={{ padding: cellPad }}><FundingCell rate={row.positioning?.funding_rate} /></td>;
    case "OI":
      return <td style={{ padding: cellPad }}><OITrendBadge trend={row.positioning?.oi_trend} /></td>;
    case "CONF":
      return <td style={{ padding: cellPad }}><ConfluenceBadge score={row.confluence?.score} label={row.confluence?.label} /></td>;
    case "PRI": {
      const pri = row.priority_score ?? 0;
      const priColor = pri >= 75 ? "#34d399" : pri >= 50 ? "#22d3ee" : pri >= 30 ? "#fbbf24" : T.text4;
      return (
        <td style={{ padding: cellPad }}>
          <span style={{
            fontFamily: T.mono, fontSize: 13, fontWeight: 700,
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
      return (
        <td style={{ padding: cellPad }}>
          <span style={{
            fontFamily: T.mono, fontSize: 13, fontWeight: 700,
            color: cm >= 8 ? "#34d399" : cm >= 5 ? "#fbbf24" : T.text4,
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

function SymbolRow({ row, selected, onSelect, visibleColumns, isMobile, backtestSymbols }) {
  const rm = REGIME_META[row.regime] || REGIME_META.FLAT;
  const isHighlight = ["STRONG_LONG", "LIGHT_LONG", "TRIM_HARD", "RISK_OFF"].includes(row.signal);

  return (
    <tr
      onClick={() => onSelect(row)}
      style={{
        cursor: "pointer",
        borderBottom: `1px solid ${T.border}`,
        background: selected ? "rgba(34,211,238,0.04)" : isHighlight ? rm.bg : "transparent",
        transition: "background 0.2s ease",
      }}
      onMouseEnter={e => { if (!selected) e.currentTarget.style.background = T.surfaceH; }}
      onMouseLeave={e => { if (!selected) e.currentTarget.style.background = selected ? "rgba(34,211,238,0.04)" : isHighlight ? rm.bg : "transparent"; }}
    >
      {visibleColumns.map(([, label]) => (
        <CellContent key={label} colLabel={label} row={row} isMobile={isMobile} backtestSymbols={backtestSymbols} />
      ))}
    </tr>
  );
}

export default function DataTable({ results, label, sortKey, onSort, selected, onSelect, visibleColumns, isMobile, backtestSymbols, loading }) {
  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      {label && (
        <div style={{
          fontFamily: T.font, fontSize: 11, color: T.text3, fontWeight: 700,
          letterSpacing: "0.12em", marginBottom: 10, paddingLeft: isMobile ? 10 : 14,
          textTransform: "uppercase",
        }}>{label}</div>
      )}
      <GlassCard style={{ overflow: "hidden" }}>
        <div style={{ overflowX: "auto", WebkitOverflowScrolling: "touch" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${T.borderH}` }}>
                {visibleColumns.map(([key, colLabel]) => (
                  <th
                    key={colLabel}
                    onClick={() => key && onSort(key)}
                    style={{
                      padding: isMobile ? "10px 8px" : "12px 10px", textAlign: "left",
                      fontFamily: T.font, fontSize: isMobile ? 11 : 12, fontWeight: 700,
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
                  color: T.text4, fontFamily: T.mono, fontSize: 11,
                }}>
                  {loading ? (
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                      <span style={{ animation: "spin 1.5s linear infinite", display: "inline-block" }}>{"\u25e0"}</span>
                      SCANNING...
                    </span>
                  ) : "NO DATA"}
                </td></tr>
              ) : (
                results.map((row) => (
                  <SymbolRow
                    key={row.symbol}
                    row={row}
                    selected={selected?.symbol === row.symbol}
                    onSelect={onSelect}
                    visibleColumns={visibleColumns}
                    isMobile={isMobile}
                    backtestSymbols={backtestSymbols}
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
