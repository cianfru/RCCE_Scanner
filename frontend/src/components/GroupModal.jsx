import { useState, useEffect, useCallback } from "react";
import { T, getBaseSymbol } from "../theme.js";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export default function GroupModal({
  editingGroup, groups, onClose, onCreateGroup, onUpdateGroup, onDeleteGroup,
  onAddSymbol, onRemoveSymbol, onLoadHyperliquidPerps, onScanNow, isMobile,
}) {
  const isEditing = editingGroup != null;
  const modalGroupId = editingGroup?.id;
  const modalSymbols = isEditing ? (groups.find(g => g.id === modalGroupId)?.symbols || []) : [];
  const usdtPairs = modalSymbols.filter(s => s.endsWith("/USDT"));
  const btcPairs = modalSymbols.filter(s => s.endsWith("/BTC"));

  const [groupName, setGroupName] = useState(isEditing ? editingGroup.name : "");
  const [groupColor, setGroupColor] = useState(isEditing ? (editingGroup.color || "#22d3ee") : "#22d3ee");
  const [watchlistSearch, setWatchlistSearch] = useState("");
  const [watchlistResults, setWatchlistResults] = useState([]);
  const [watchlistLoading, setWatchlistLoading] = useState(false);
  const [hlPerpsLoading, setHlPerpsLoading] = useState(false);

  const searchSymbols = useCallback(async (q) => {
    if (!q || q.length < 1) { setWatchlistResults([]); return; }
    setWatchlistLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/watchlist/search?q=${encodeURIComponent(q)}`);
      const data = await res.json();
      setWatchlistResults(data.results || []);
    } catch (_) {
      setWatchlistResults([]);
    } finally {
      setWatchlistLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => searchSymbols(watchlistSearch), 300);
    return () => clearTimeout(timer);
  }, [watchlistSearch, searchSymbols]);

  const handleLoadHyperliquidPerps = async () => {
    setHlPerpsLoading(true);
    await onLoadHyperliquidPerps(modalGroupId);
    setHlPerpsLoading(false);
  };

  return (
    <>
      <div
        onClick={onClose}
        style={{
          position: "fixed", inset: 0, zIndex: 299,
          background: T.shadowDeep,
        }}
      />
      <div style={{
        position: "fixed",
        top: isMobile ? "5%" : "50%",
        left: isMobile ? "3%" : "50%",
        transform: isMobile ? "none" : "translate(-50%, -50%)",
        width: isMobile ? "94%" : 480,
        maxHeight: isMobile ? "90vh" : "80vh",
        background: T.popoverBg,
        backdropFilter: "blur(40px) saturate(1.5)", WebkitBackdropFilter: "blur(40px) saturate(1.5)",
        border: `1px solid ${T.borderH}`,
        borderRadius: T.radius,
        zIndex: 300,
        display: "flex", flexDirection: "column",
        boxShadow: `0 24px 80px ${T.shadowHeavy}, 0 0 1px ${T.overlay10}`,
      }}>
        {/* Modal Header */}
        <div style={{
          padding: "18px 20px", borderBottom: `1px solid ${T.border}`,
          display: "flex", justifyContent: "space-between", alignItems: "center",
        }}>
          <div style={{ flex: 1 }}>
            {isEditing ? (
              <>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <input
                    type="text"
                    value={groupName}
                    onChange={e => setGroupName(e.target.value)}
                    onBlur={() => { if (groupName && groupName !== editingGroup.name) onUpdateGroup(modalGroupId, { name: groupName }); }}
                    style={{
                      fontSize: 15, fontWeight: 700, color: T.text1, fontFamily: T.font,
                      letterSpacing: "-0.01em", background: "transparent", border: "none",
                      borderBottom: `1px solid ${T.border}`, outline: "none",
                      padding: "2px 0", width: "auto", minWidth: 100,
                    }}
                  />
                  <div style={{ display: "flex", gap: 4 }}>
                    {["#22d3ee", "#34d399", "#fb923c", "#f87171", "#c084fc", "#fbbf24", "#67e8f9"].map(c => (
                      <span
                        key={c}
                        onClick={() => { setGroupColor(c); onUpdateGroup(modalGroupId, { color: c }); }}
                        style={{
                          width: 16, height: 16, borderRadius: "50%", cursor: "pointer",
                          background: c,
                          border: groupColor === c ? "2px solid white" : "2px solid transparent",
                          transition: "border 0.15s",
                        }}
                      />
                    ))}
                  </div>
                </div>
                <div style={{ fontSize: 10, color: T.text4, fontFamily: T.mono, marginTop: 3 }}>
                  {modalSymbols.length} symbols {editingGroup.pinned && "\u00b7 Pinned"}
                </div>
              </>
            ) : (
              <>
                <div style={{ fontSize: 15, fontWeight: 700, color: T.text1, fontFamily: T.font, letterSpacing: "-0.01em" }}>
                  Create New Group
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 8 }}>
                  <input
                    type="text"
                    placeholder="Group name (e.g. Memes, L1, DeFi)..."
                    value={groupName}
                    onChange={e => setGroupName(e.target.value)}
                    style={{
                      flex: 1, padding: "8px 12px",
                      background: T.surface, border: `1px solid ${T.border}`,
                      borderRadius: T.radiusSm, color: T.text1,
                      fontFamily: T.mono, fontSize: 12, outline: "none",
                    }}
                  />
                  <div style={{ display: "flex", gap: 3 }}>
                    {["#22d3ee", "#34d399", "#fb923c", "#f87171", "#c084fc", "#fbbf24"].map(c => (
                      <span
                        key={c}
                        onClick={() => setGroupColor(c)}
                        style={{
                          width: 14, height: 14, borderRadius: "50%", cursor: "pointer",
                          background: c,
                          border: groupColor === c ? "2px solid white" : "2px solid transparent",
                        }}
                      />
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
          <button
            className="apple-btn"
            onClick={onClose}
            style={{
              borderRadius: "50%", width: 28, height: 28, padding: 0,
              fontSize: 12, flexShrink: 0, marginLeft: 12,
              display: "flex", alignItems: "center", justifyContent: "center",
            }}
          >{"\u2715"}</button>
        </div>

        {/* Search (edit mode) */}
        {isEditing && (
          <div style={{ padding: "12px 20px", borderBottom: `1px solid ${T.border}` }}>
            <div style={{ position: "relative" }}>
              <input
                type="text"
                placeholder="Search symbols to add (e.g. DOGE, SUI)..."
                value={watchlistSearch}
                onChange={e => setWatchlistSearch(e.target.value)}
                style={{
                  width: "100%", padding: "10px 14px", paddingLeft: 36,
                  background: T.surface, border: `1px solid ${T.border}`,
                  borderRadius: T.radiusSm, color: T.text1,
                  fontFamily: T.mono, fontSize: 12, outline: "none",
                  transition: "border-color 0.2s",
                }}
                onFocus={e => e.target.style.borderColor = T.accent + "40"}
                onBlur={e => e.target.style.borderColor = T.border}
              />
              <span style={{
                position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)",
                fontSize: 14, color: T.text4,
              }}>{"\ud83d\udd0d"}</span>
            </div>

            {watchlistSearch && watchlistResults.length > 0 && (
              <div style={{
                marginTop: 6, maxHeight: 200, overflowY: "auto",
                background: "rgba(24,24,27,0.98)", border: `1px solid ${T.border}`,
                borderRadius: T.radiusSm,
              }}>
                {watchlistResults.slice(0, 20).map(r => {
                  const inList = modalSymbols.includes(r.symbol);
                  return (
                    <div
                      key={r.symbol}
                      onClick={() => !inList && onAddSymbol(modalGroupId, r.symbol)}
                      style={{
                        padding: "8px 14px", cursor: inList ? "default" : "pointer",
                        display: "flex", justifyContent: "space-between", alignItems: "center",
                        borderBottom: `1px solid ${T.border}`,
                        opacity: inList ? 0.4 : 1,
                        transition: "background 0.15s",
                      }}
                      onMouseEnter={e => { if (!inList) e.currentTarget.style.background = T.surfaceH; }}
                      onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                    >
                      <span style={{ fontFamily: T.mono, fontSize: 11, color: T.text1, fontWeight: 500 }}>
                        {r.base}<span style={{ color: r.quote === "BTC" ? "#fb923c" : T.text4 }}>/{r.quote}</span>
                      </span>
                      {inList ? (
                        <span style={{ fontSize: 9, color: T.text4, fontFamily: T.mono }}>{"\u2713"} Added</span>
                      ) : (
                        <span style={{ fontSize: 9, color: T.accent, fontFamily: T.mono, fontWeight: 600 }}>+ Add</span>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
            {watchlistSearch && watchlistResults.length === 0 && !watchlistLoading && (
              <div style={{ marginTop: 8, fontSize: 10, color: T.text4, fontFamily: T.mono, textAlign: "center" }}>
                No matches found
              </div>
            )}
          </div>
        )}

        {/* Symbol chips (edit mode) */}
        {isEditing && (
          <div style={{ flex: 1, overflowY: "auto", padding: "12px 20px" }}>
            {usdtPairs.length > 0 && (
              <>
                <div style={{
                  fontSize: 9, fontFamily: T.mono, color: T.text4,
                  fontWeight: 600, letterSpacing: "0.08em",
                  marginBottom: 6, textTransform: "uppercase",
                }}>
                  USDT Pairs ({usdtPairs.length})
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {usdtPairs.map(sym => (
                    <span
                      key={sym}
                      style={{
                        display: "inline-flex", alignItems: "center", gap: 6,
                        padding: "5px 10px", borderRadius: "20px",
                        background: T.surface, border: `1px solid ${T.border}`,
                        fontFamily: T.mono, fontSize: 10, color: T.text2, fontWeight: 500,
                      }}
                    >
                      {getBaseSymbol(sym)}
                      <span
                        onClick={() => onRemoveSymbol(modalGroupId, sym)}
                        style={{ cursor: "pointer", color: T.text4, fontSize: 10, display: "flex", alignItems: "center", transition: "color 0.15s" }}
                        onMouseEnter={e => e.currentTarget.style.color = "#f87171"}
                        onMouseLeave={e => e.currentTarget.style.color = T.text4}
                      >{"\u2715"}</span>
                    </span>
                  ))}
                </div>
              </>
            )}
            {btcPairs.length > 0 && (
              <>
                <div style={{
                  fontSize: 9, fontFamily: T.mono, color: "#fb923c",
                  fontWeight: 600, letterSpacing: "0.08em",
                  marginTop: usdtPairs.length > 0 ? 14 : 0, marginBottom: 6,
                  textTransform: "uppercase",
                }}>
                  BTC Pairs ({btcPairs.length})
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {btcPairs.map(sym => (
                    <span
                      key={sym}
                      style={{
                        display: "inline-flex", alignItems: "center", gap: 6,
                        padding: "5px 10px", borderRadius: "20px",
                        background: T.surface, border: `1px solid rgba(251,146,60,0.25)`,
                        fontFamily: T.mono, fontSize: 10, color: T.text2, fontWeight: 500,
                      }}
                    >
                      {getBaseSymbol(sym)}
                      <span
                        onClick={() => onRemoveSymbol(modalGroupId, sym)}
                        style={{ cursor: "pointer", color: T.text4, fontSize: 10, display: "flex", alignItems: "center", transition: "color 0.15s" }}
                        onMouseEnter={e => e.currentTarget.style.color = "#f87171"}
                        onMouseLeave={e => e.currentTarget.style.color = T.text4}
                      >{"\u2715"}</span>
                    </span>
                  ))}
                </div>
              </>
            )}
            {modalSymbols.length === 0 && (
              <div style={{ padding: "30px 0", textAlign: "center", color: T.text4, fontFamily: T.mono, fontSize: 11 }}>
                No symbols yet. Use the search above to add symbols.
              </div>
            )}
          </div>
        )}

        {/* Modal Footer */}
        <div style={{
          padding: "12px 20px", borderTop: `1px solid ${T.border}`,
          display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8,
        }}>
          {isEditing ? (
            <>
              {!editingGroup.pinned && (
                <button
                  className="apple-btn"
                  onClick={async () => { await onDeleteGroup(modalGroupId); onClose(); }}
                  style={{
                    padding: "8px 16px", fontFamily: T.mono, fontSize: 10, fontWeight: 500,
                    letterSpacing: "0.04em", color: "#f87171", borderColor: "rgba(248,113,113,0.2)",
                  }}
                >
                  Delete Group
                </button>
              )}
              <div style={{ flex: 1 }} />
              <button
                className="apple-btn"
                onClick={handleLoadHyperliquidPerps}
                disabled={hlPerpsLoading}
                style={{
                  padding: "8px 14px", fontFamily: T.mono, fontSize: 10, fontWeight: 600,
                  letterSpacing: "0.04em", color: "#fb923c", borderColor: "rgba(251,146,60,0.2)",
                  opacity: hlPerpsLoading ? 0.5 : 1,
                }}
              >
                {hlPerpsLoading ? "Loading..." : "+ Hyperliquid Perps"}
              </button>
              <button
                className="apple-btn apple-btn-accent"
                onClick={() => { onClose(); onScanNow(); }}
                style={{
                  padding: "8px 22px", fontFamily: T.mono, fontSize: 10, fontWeight: 700,
                  letterSpacing: "0.06em",
                }}
              >
                Scan Now
              </button>
            </>
          ) : (
            <>
              <button
                className="apple-btn"
                onClick={onClose}
                style={{
                  padding: "8px 18px", fontFamily: T.mono, fontSize: 10, fontWeight: 500,
                  letterSpacing: "0.04em",
                }}
              >
                Cancel
              </button>
              <button
                className="apple-btn apple-btn-accent"
                disabled={!groupName.trim()}
                onClick={async () => {
                  const g = await onCreateGroup(groupName.trim(), [], groupColor);
                  if (g) {
                    // Switch to edit mode for the new group
                    onClose();
                  }
                }}
                style={{
                  padding: "8px 22px", fontFamily: T.mono, fontSize: 10, fontWeight: 700,
                  letterSpacing: "0.06em", opacity: groupName.trim() ? 1 : 0.4,
                }}
              >
                Create Group
              </button>
            </>
          )}
        </div>
      </div>
    </>
  );
}
