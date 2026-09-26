import { useState, useMemo, useCallback, useEffect } from "react";
import { T, m, fmt } from "../theme.js";
import {
  RegimeBadge, SignalDot, ZScoreBar, HeatCell, ConfluenceBadge,
} from "./badges.jsx";
import SparklineCell from "./SparklineCell.jsx";
import GlassCard from "./GlassCard.jsx";
import InfoButton from "./InfoPopover.jsx";
import Tabs from "./Tabs.jsx";
import { getAdminKey } from "../auth.js";
import { formatPrice } from "../utils/marketPresentation.js";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const CATEGORIES = ["ALL", "Commodities", "Indices", "Equities", "ETFs"];
const ADD_CATEGORIES = ["Equities", "Commodities", "Indices", "ETFs"];
const REGIME_ORDER = ["MARKUP", "REACC", "BLOWOFF", "CAP", "MARKDOWN", "ACCUM", "ABSORBING", "FLAT"];
// Strongest entries first, then WAIT, then exits.
const SIGNAL_ORDER = ["STRONG_LONG", "LIGHT_LONG", "ACCUMULATE", "REVIVAL_SEED_CONFIRMED", "REVIVAL_SEED", "WAIT",
  "NO_LONG", "TRIM", "TRIM_HARD", "RISK_OFF", "LIGHT_SHORT", "STRONG_SHORT"];
const rank = (order, v) => { const i = order.indexOf(v); return i < 0 ? order.length : i; };

// The timeframe tabs sit in the page title row (App.jsx); tfView comes from there.
export default function TradFiPanel({
  results, data4h, data1d, tfView = "1d",
  selected, onSelect, isMobile, loading,
}) {
  const [category, setCategory] = useState("ALL");
  // Local sort: TradFi headers must not re-sort the perps and spot tables.
  const [sortKey, setSortKey] = useState("priority_score");
  const [managing, setManaging] = useState(false);
  const [symbols, setSymbols] = useState([]);
  const [addForm, setAddForm] = useState({ coin: "", name: "", category: "Equities", yf: "" });
  const [addError, setAddError] = useState("");
  const canManage = !!getAdminKey();   // adding or removing markets needs the admin key

  // Clean coin input: strip common pair suffixes the user might add
  const cleanCoin = (raw) => raw.toUpperCase().replace(/[/-](USDC?|USDT|USD)$/i, "");

  const loadSymbols = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/tradfi/symbols`);
      const data = await res.json();
      setSymbols(data.symbols || []);
    } catch (_) {}
  }, []);

  useEffect(() => { if (managing) loadSymbols(); }, [managing, loadSymbols]);

  const handleAdd = async () => {
    setAddError("");
    const { coin, name, yf } = addForm;
    if (!coin.trim() || !name.trim() || !yf.trim()) {
      setAddError("All fields required"); return;
    }
    try {
      const res = await fetch(`${API_BASE}/api/tradfi/symbols`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(addForm),
      });
      const data = await res.json();
      if (!res.ok) { setAddError(data.error || "Failed"); return; }
      setAddForm({ coin: "", name: "", category: "Equities", yf: "" });
      await loadSymbols();
    } catch (_) { setAddError("Network error"); }
  };

  const handleRemove = async (coin) => {
    try {
      await fetch(`${API_BASE}/api/tradfi/symbols/${encodeURIComponent(coin)}`, { method: "DELETE" });
      await loadSymbols();
    } catch (_) {}
  };

  // Pick the right dataset based on timeframe toggle
  const activeData = tfView === "4h" ? data4h : data1d;

  // Category counts; only categories with markets get a tab.
  const counts = useMemo(() => {
    const c = { ALL: activeData.length };
    for (const r of activeData) if (r.asset_class) c[r.asset_class] = (c[r.asset_class] || 0) + 1;
    return c;
  }, [activeData]);
  const categories = ["ALL", ...CATEGORIES.slice(1).filter(cat => counts[cat] > 0),
    ...Object.keys(counts).filter(cat => cat !== "ALL" && !CATEGORIES.includes(cat))];
  const activeCategory = categories.includes(category) ? category : "ALL";

  const filtered = useMemo(() => {
    if (activeCategory === "ALL") return activeData;
    return activeData.filter(r => r.asset_class === activeCategory);
  }, [activeData, activeCategory]);

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      if (sortKey === "priority_score") return (b.priority_score || 0) - (a.priority_score || 0);
      if (sortKey === "momentum") return (b.momentum || 0) - (a.momentum || 0);
      if (sortKey === "zscore") return (b.zscore || 0) - (a.zscore || 0);
      if (sortKey === "heat") return (b.heat || 0) - (a.heat || 0);
      if (sortKey === "regime") return rank(REGIME_ORDER, a.regime) - rank(REGIME_ORDER, b.regime);
      if (sortKey === "signal") return rank(SIGNAL_ORDER, a.signal) - rank(SIGNAL_ORDER, b.signal);
      return 0;
    });
  }, [filtered, sortKey]);

  // Regime summary (markets without candle history have no measured regime)
  const regimeSummary = useMemo(() => {
    const s = {};
    for (const r of sorted) {
      if (r.history_bars === 0) continue;
      s[r.regime] = (s[r.regime] || 0) + 1;
    }
    return s;
  }, [sorted]);

  const cellPad = isMobile ? `${T.sp2 + 2}px ${T.sp2 + 2}px` : `${T.sp3}px ${T.sp3}px`;
  // Every sort is descending; the active column carries the arrow.
  // info: the scanner's column-help key (same explanations as the crypto table).
  const sortTh = (key, label, info = label) => (
    <th key={key} style={{ ...thStyle(isMobile), cursor: "pointer", color: sortKey === key ? T.text2 : T.text4 }}
      aria-sort={sortKey === key ? "descending" : "none"} onClick={() => setSortKey(key)}>
      <span style={{ display: "inline-flex", alignItems: "center" }}>
        {label}{sortKey === key ? " \u25bc" : ""}{info && <InfoButton label={info} />}
      </span>
    </th>
  );

  return (
    <div style={{ marginTop: isMobile ? 16 : 20 }}>
      {/* Subtitle + Manage (admin only) */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        flexWrap: "wrap", gap: 12, marginBottom: 16,
      }}>
        <span style={{ fontFamily: T.font, fontSize: m(T.textSm, isMobile), color: T.text3 }}>HIP-3 markets</span>
        {canManage && (
          <button type="button" aria-pressed={managing} onClick={() => setManaging(!managing)} style={{
            border: "none", background: "transparent", padding: 0, cursor: "pointer",
            fontFamily: T.font, fontSize: m(T.textSm, isMobile),
            color: managing ? T.text1 : T.text3,
            textDecoration: "underline", textUnderlineOffset: 3,
          }}>
            {managing ? "Done" : "+ Manage"}
          </button>
        )}
      </div>

      {/* Category filter: the shared tab style */}
      <div style={{ marginBottom: 14 }}>
        <Tabs small label="Category" value={activeCategory} onChange={setCategory}
          items={categories.map(cat => ({ key: cat, label: `${cat === "ALL" ? "All" : cat}${counts[cat] > 0 ? ` ${counts[cat]}` : ""}` }))} />
      </div>

      {/* Manage panel */}
      {managing && canManage && (
        <GlassCard style={{ marginBottom: 14, padding: isMobile ? 14 : 16 }}>
          {/* Add form */}
          <div style={{
            fontFamily: T.mono, fontSize: m(T.textSm, isMobile), fontWeight: 600,
            color: T.text2, marginBottom: 10,
          }}>
            Add Market
          </div>
          <div style={{
            display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 12,
          }}>
            <input
              placeholder="HL ticker (e.g. META)"
              value={addForm.coin}
              onChange={e => setAddForm(f => ({ ...f, coin: cleanCoin(e.target.value) }))}
              style={{
                fontFamily: T.mono, fontSize: m(T.textSm, isMobile), padding: "6px 10px",
                borderRadius: 6, border: `1px solid ${T.border}`, background: T.surface,
                color: T.text1, width: 130, outline: "none",
              }}
            />
            <input
              placeholder="Name (e.g. Meta Platforms)"
              value={addForm.name}
              onChange={e => setAddForm(f => ({ ...f, name: e.target.value }))}
              style={{
                fontFamily: T.mono, fontSize: m(T.textSm, isMobile), padding: "6px 10px",
                borderRadius: 6, border: `1px solid ${T.border}`, background: T.surface,
                color: T.text1, flex: 1, minWidth: 140, outline: "none",
              }}
            />
            <input
              placeholder="YF Ticker (e.g. META)"
              value={addForm.yf}
              onChange={e => setAddForm(f => ({ ...f, yf: e.target.value }))}
              style={{
                fontFamily: T.mono, fontSize: m(T.textSm, isMobile), padding: "6px 10px",
                borderRadius: 6, border: `1px solid ${T.border}`, background: T.surface,
                color: T.text1, width: 130, outline: "none",
              }}
            />
            <select
              value={addForm.category}
              onChange={e => setAddForm(f => ({ ...f, category: e.target.value }))}
              style={{
                fontFamily: T.mono, fontSize: m(T.textSm, isMobile), padding: "6px 10px",
                borderRadius: 6, border: `1px solid ${T.border}`, background: T.surface,
                color: T.text1, outline: "none",
              }}
            >
              {ADD_CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
            <button onClick={handleAdd} style={{
              fontFamily: T.mono, fontSize: m(T.textSm, isMobile), fontWeight: 600,
              padding: "6px 16px", borderRadius: 6, cursor: "pointer",
              border: `1px solid ${T.green}60`, background: `${T.green}18`,
              color: T.green, transition: "all 0.15s ease",
            }}>
              Add
            </button>
          </div>
          {addForm.coin && (
            <div style={{
              fontFamily: T.mono, fontSize: m(T.textXs, isMobile), color: T.text4,
              marginBottom: 8, paddingLeft: 2,
            }}>
              Symbol will be: <span style={{ color: T.accent, fontWeight: 600 }}>{addForm.coin}/USD</span>
            </div>
          )}
          {addError && (
            <div style={{
              fontFamily: T.mono, fontSize: T.textXs, color: T.red, marginBottom: 10,
            }}>
              {addError}
            </div>
          )}

          {/* Current symbols list */}
          <div style={{
            fontFamily: T.mono, fontSize: m(T.textSm, isMobile), fontWeight: 600,
            color: T.text2, marginBottom: 8,
          }}>
            Current Markets ({symbols.length})
          </div>
          <div style={{
            display: "flex", flexWrap: "wrap", gap: 6,
          }}>
            {symbols.map(s => (
              <div key={s.coin} style={{
                display: "flex", alignItems: "center", gap: 6,
                fontFamily: T.mono, fontSize: m(T.textXs, isMobile),
                padding: "4px 10px", borderRadius: 4,
                border: `1px solid ${T.border}`, background: T.surface,
                color: T.text2,
              }}>
                <span style={{ fontWeight: 600 }}>{s.coin}</span>
                <span style={{ color: T.text4 }}>{s.name}</span>
                <span style={{ color: T.text4, fontSize: T.textXs }}>({s.category})</span>
                <button
                  onClick={() => handleRemove(s.coin)}
                  style={{
                    background: "none", border: "none", cursor: "pointer",
                    color: T.red, fontFamily: T.mono, fontWeight: 700,
                    fontSize: 14, padding: "0 2px", lineHeight: 1,
                    opacity: 0.6, transition: "opacity 0.15s",
                  }}
                  onMouseEnter={e => e.target.style.opacity = 1}
                  onMouseLeave={e => e.target.style.opacity = 0.6}
                  title={`Remove ${s.coin}`}
                >
                  x
                </button>
              </div>
            ))}
          </div>
        </GlassCard>
      )}

      {/* Regime summary bar */}
      {Object.keys(regimeSummary).length > 0 && (
        <div style={{
          display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 14,
          fontFamily: T.mono, fontSize: T.textXs, color: T.text4,
        }}>
          {Object.entries(regimeSummary).map(([regime, count]) => (
            <span key={regime} style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <RegimeBadge regime={regime} />
              <span style={{ color: T.text3 }}>{count}</span>
            </span>
          ))}
        </div>
      )}

      {/* Results table */}
      <GlassCard style={{ padding: 0, overflow: "hidden" }}>
        {loading && sorted.length === 0 ? (
          <div style={{
            padding: 40, textAlign: "center", fontFamily: T.mono,
            fontSize: m(T.textSm, isMobile), color: T.text4,
          }}>
            Scanning TradFi markets...
          </div>
        ) : sorted.length === 0 ? (
          <div style={{
            padding: 40, textAlign: "center", fontFamily: T.mono,
            fontSize: m(T.textSm, isMobile), color: T.text4,
          }}>
            {activeData.length ? "No markets in this category." : "No TradFi data yet — waiting for first scan"}
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{
              width: "100%", borderCollapse: "collapse", fontFamily: T.font,
              tableLayout: "auto",
            }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                  <th style={{ ...thStyle(isMobile), width: 28 }}>#</th>
                  <th style={thStyle(isMobile)}>ASSET</th>
                  {!isMobile && <th style={thStyle(isMobile)}>CATEGORY</th>}
                  {isMobile ? sortTh("regime", "REGIME / SIGNAL", "REGIME") : <>{sortTh("regime", "REGIME")}{sortTh("signal", "SIGNAL")}</>}
                  {!isMobile && <th style={thStyle(isMobile)}>SPARK</th>}
                  {!isMobile && sortTh("zscore", "Z-SCORE")}
                  {sortTh("momentum", "MOM")}
                  {!isMobile && sortTh("heat", "HEAT")}
                  {!isMobile && <th style={thStyle(isMobile)}><span style={{ display: "inline-flex", alignItems: "center" }}>CONF<InfoButton label="CONF" /></span></th>}
                  {sortTh("priority_score", "PRI")}
                </tr>
              </thead>
              <tbody>
                {sorted.map((r, i) => {
                  const isSelected = selected?.symbol === r.symbol;
                  const noHistory = r.history_bars === 0;   // unmeasured, not zero
                  // Colour follows the shown value: 0.03 prints as 0.0% and stays neutral.
                  const mom1 = r.momentum == null ? null : Math.round(r.momentum * 10) / 10 || 0;
                  return (
                    <tr
                      key={r.symbol}
                      onClick={() => onSelect(r)}
                      style={{
                        cursor: "pointer",
                        borderBottom: `1px solid ${T.border}22`,
                        background: isSelected ? `${T.cyan}0a` : "transparent",
                        transition: "background 0.15s ease",
                      }}
                      onMouseEnter={e => e.currentTarget.style.background = `${T.cyan}08`}
                      onMouseLeave={e => e.currentTarget.style.background = isSelected ? `${T.cyan}0a` : "transparent"}
                    >
                      <td style={{ padding: cellPad, fontFamily: T.mono, fontSize: m(T.textXs, isMobile), color: T.text4, textAlign: "center" }}>
                        {i + 1}
                      </td>
                      <td style={{ padding: cellPad }}>
                        {isMobile ? <>
                          <div style={{ fontFamily: T.mono, whiteSpace: "nowrap" }}>
                            <span style={{ fontWeight: 700, color: T.text1, fontSize: m(T.textBase, isMobile) }}>{r.tradfi_coin || r.symbol.split("/")[0]}</span>
                            <span style={{ color: T.text3, fontSize: m(T.textXs, isMobile), marginLeft: 6 }}>{formatPrice(r.price)}</span>
                          </div>
                          <div style={{ fontFamily: T.mono, fontSize: m(T.textXs, isMobile), color: T.text4, marginTop: 2, maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {r.tradfi_name || r.symbol}
                          </div>
                        </> : <>
                          <div style={{ fontFamily: T.mono, fontWeight: 700, color: T.text1, fontSize: m(T.textMd, isMobile) }}>
                            {r.tradfi_coin || r.symbol.split("/")[0]}
                          </div>
                          <div style={{ fontFamily: T.mono, fontSize: m(T.textXs, isMobile), color: T.text4, marginTop: 2 }}>
                            {r.tradfi_name || r.symbol} — {formatPrice(r.price)}
                          </div>
                        </>}
                      </td>
                      {!isMobile && <td style={{ padding: cellPad, fontFamily: T.font, fontSize: m(T.textXs, isMobile), color: T.text3 }}>
                        {r.asset_class}
                      </td>}
                      {isMobile ? (
                        <td style={{ padding: cellPad }}>
                          <div><RegimeBadge regime={r.regime} isMobile={isMobile} noHistory={noHistory} /></div>
                          <div style={{ marginTop: 4 }}><SignalDot signal={r.signal} reason={r.signal_reason} warnings={r.signal_warnings} isMobile={isMobile} /></div>
                        </td>
                      ) : <>
                        <td style={{ padding: cellPad }}><RegimeBadge regime={r.regime} isMobile={isMobile} noHistory={noHistory} /></td>
                        <td style={{ padding: cellPad }}><SignalDot signal={r.signal} reason={r.signal_reason} warnings={r.signal_warnings} isMobile={isMobile} /></td>
                        <td style={{ padding: cellPad }}><SparklineCell data={r.sparkline} width={72} height={22} /></td>
                        <td style={{ padding: cellPad }}>{noHistory ? <span style={{ color: T.text4 }}>—</span> : <ZScoreBar z={r.zscore} isMobile={isMobile} />}</td>
                      </>}
                      <td style={{
                        padding: cellPad, fontFamily: T.mono,
                        fontSize: m(isMobile ? T.textBase : T.textMd, isMobile),
                        color: noHistory || mom1 == null ? T.text4 : mom1 > 0 ? T.green : mom1 < 0 ? T.red : T.text3,
                      }}>
                        {noHistory ? "—" : `${fmt(mom1, 1)}%`}
                      </td>
                      {!isMobile && <td style={{ padding: cellPad }}><HeatCell heat={r.heat} phase={r.heat_phase} isMobile={isMobile} /></td>}
                      {!isMobile && <td style={{ padding: cellPad }}>
                        {r.confluence ? <ConfluenceBadge score={r.confluence.score} label={r.confluence.label} /> : <span style={{ color: T.text4 }}>—</span>}
                      </td>}
                      <td style={{
                        padding: cellPad, fontFamily: T.mono,
                        fontSize: m(T.textSm, isMobile), fontWeight: 600,
                        color: (r.priority_score || 0) >= 60 ? T.green : (r.priority_score || 0) >= 30 ? T.yellow : T.text4,
                      }}>
                        {Math.round(r.priority_score || 0)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </GlassCard>
    </div>
  );
}

function thStyle(isMobile) {
  return {
    padding: isMobile ? `${T.sp2 + 2}px ${T.sp2 + 2}px` : `${T.sp3}px ${T.sp3}px`,
    fontFamily: T.mono,
    fontSize: m(T.textXs, isMobile),
    fontWeight: 700,
    color: T.text4,
    textAlign: "left",
    letterSpacing: "0.06em",
    whiteSpace: "nowrap",
    userSelect: "none",
  };
}
