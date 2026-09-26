import { useState, useMemo, useCallback, useEffect } from "react";
import { T, m, fmt } from "../theme.js";
import {
  RegimeBadge, SignalDot, ZScoreBar, HeatCell, ConfluenceBadge,
} from "./badges.jsx";
import SparklineCell from "./SparklineCell.jsx";
import GlassCard from "./GlassCard.jsx";
import Tabs from "./Tabs.jsx";
import { getAdminKey } from "../auth.js";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const CATEGORIES = ["ALL", "Commodities", "Indices", "Equities", "ETFs"];
const ADD_CATEGORIES = ["Equities", "Commodities", "Indices", "ETFs"];

// The timeframe tabs sit in the page title row (App.jsx); tfView comes from there.
export default function TradFiPanel({
  results, data4h, data1d, tfView = "1d",
  sortKey, onSort, selected, onSelect,
  visibleColumns, isMobile, loading,
}) {
  const [category, setCategory] = useState("ALL");
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

  const filtered = useMemo(() => {
    if (category === "ALL") return activeData;
    return activeData.filter(r => r.asset_class === category);
  }, [activeData, category]);

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      if (sortKey === "priority_score") return (b.priority_score || 0) - (a.priority_score || 0);
      if (sortKey === "momentum") return (b.momentum || 0) - (a.momentum || 0);
      if (sortKey === "zscore") return (b.zscore || 0) - (a.zscore || 0);
      if (sortKey === "heat") return (b.heat || 0) - (a.heat || 0);
      if (sortKey === "regime") {
        const REGIME_ORDER = ["MARKUP", "REACCUMULATION", "BLOWOFF", "CAP_ZONE", "MARKDOWN", "ACCUMULATION", "FLAT"];
        return REGIME_ORDER.indexOf(a.regime) - REGIME_ORDER.indexOf(b.regime);
      }
      return 0;
    });
  }, [filtered, sortKey]);

  // Category counts
  const counts = useMemo(() => {
    const c = { ALL: activeData.length };
    for (const cat of CATEGORIES.slice(1)) {
      c[cat] = activeData.filter(r => r.asset_class === cat).length;
    }
    return c;
  }, [activeData]);

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
        <Tabs small label="Category" value={category} onChange={setCategory}
          items={CATEGORIES.map(cat => ({ key: cat, label: `${cat === "ALL" ? "All" : cat}${counts[cat] > 0 ? ` ${counts[cat]}` : ""}` }))} />
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
            No TradFi data yet — waiting for first scan
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
                  <th style={thStyle(isMobile)}>CATEGORY</th>
                  <th style={{ ...thStyle(isMobile), cursor: "pointer" }} onClick={() => onSort("regime")}>REGIME</th>
                  <th style={{ ...thStyle(isMobile), cursor: "pointer" }} onClick={() => onSort("signal")}>SIGNAL</th>
                  <th style={thStyle(isMobile)}>SPARK</th>
                  <th style={{ ...thStyle(isMobile), cursor: "pointer" }} onClick={() => onSort("zscore")}>Z-SCORE</th>
                  <th style={{ ...thStyle(isMobile), cursor: "pointer" }} onClick={() => onSort("momentum")}>MOM</th>
                  <th style={{ ...thStyle(isMobile), cursor: "pointer" }} onClick={() => onSort("heat")}>HEAT</th>
                  <th style={thStyle(isMobile)}>CONF</th>
                  <th style={{ ...thStyle(isMobile), cursor: "pointer" }} onClick={() => onSort("priority_score")}>PRI</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((r, i) => {
                  const isSelected = selected?.symbol === r.symbol;
                  const noHistory = r.history_bars === 0;   // unmeasured, not zero
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
                        <div style={{ fontFamily: T.mono, fontWeight: 700, color: T.text1, fontSize: m(isMobile ? T.textBase : T.textMd, isMobile) }}>
                          {r.tradfi_coin || r.symbol.split("/")[0]}
                        </div>
                        <div style={{ fontFamily: T.mono, fontSize: m(T.textXs, isMobile), color: T.text4, marginTop: 2 }}>
                          {r.tradfi_name || r.symbol} — ${fmt(r.price, r.price > 100 ? 2 : 4)}
                        </div>
                      </td>
                      <td style={{ padding: cellPad, fontFamily: T.font, fontSize: m(T.textXs, isMobile), color: T.text3 }}>
                        {r.asset_class}
                      </td>
                      <td style={{ padding: cellPad }}><RegimeBadge regime={r.regime} isMobile={isMobile} noHistory={noHistory} /></td>
                      <td style={{ padding: cellPad }}><SignalDot signal={r.signal} reason={r.signal_reason} warnings={r.signal_warnings} isMobile={isMobile} /></td>
                      <td style={{ padding: cellPad }}><SparklineCell data={r.sparkline} width={72} height={22} /></td>
                      <td style={{ padding: cellPad }}>{noHistory ? <span style={{ color: T.text4 }}>—</span> : <ZScoreBar z={r.zscore} isMobile={isMobile} />}</td>
                      <td style={{
                        padding: cellPad, fontFamily: T.mono,
                        fontSize: m(isMobile ? T.textBase : T.textMd, isMobile),
                        color: noHistory ? T.text4 : (r.momentum || 0) > 0 ? T.green : (r.momentum || 0) < 0 ? T.red : T.text3,
                      }}>
                        {noHistory ? "—" : `${fmt(r.momentum, 1)}%`}
                      </td>
                      <td style={{ padding: cellPad }}><HeatCell heat={r.heat} phase={r.heat_phase} isMobile={isMobile} /></td>
                      <td style={{ padding: cellPad }}>
                        {r.confluence ? <ConfluenceBadge score={r.confluence.score} label={r.confluence.label} /> : <span style={{ color: T.text4 }}>—</span>}
                      </td>
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
