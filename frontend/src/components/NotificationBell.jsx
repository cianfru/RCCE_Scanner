import { useState, useEffect, useRef, useCallback } from "react";
import { T } from "../theme";
import { useWallet } from "../WalletContext.jsx";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const TRANSITION_COLORS = {
  ENTRY:     "#22c55e",
  UPGRADE:   "#22c55e",
  EXIT:      "#ef4444",
  DOWNGRADE: "#ef4444",
};

const TRANSITION_ICONS = {
  ENTRY:     "\u25b2",  // ▲
  UPGRADE:   "\u25b2",
  EXIT:      "\u25bc",  // ▼
  DOWNGRADE: "\u25bc",
  regime:    "\u25c6",  // ◆
};

const SEVERITY_COLORS = {
  critical: "#ef4444",
  high:     "#f59e0b",
  medium:   "#eab308",
  low:      "#6b7280",
  positive: "#34d399",
};

const SEVERITY_ICONS = {
  critical: "\u26a0",  // ⚠
  high:     "\u26a0",
  medium:   "\u25cb",  // ○
  low:      "\u00b7",  // ·
  positive: "\u25b2",  // ▲ entry setup
};

const DISMISSED_KEY = "rcce-bell-dismissed";

function getDismissed() {
  try {
    const raw = sessionStorage.getItem(DISMISSED_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch { return []; }
}

function saveDismissed(list) {
  sessionStorage.setItem(DISMISSED_KEY, JSON.stringify(list));
}

function timeAgo(ts) {
  const diff = Math.floor(Date.now() / 1000) - ts;
  if (diff < 60) return "now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return `${Math.floor(diff / 86400)}d`;
}

function coinName(symbol) {
  return symbol.replace("/USDT", "").replace("/USD", "");
}

/* Dismiss button (X) — reused across all sections */
function DismissBtn({ onClick }) {
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      style={{
        fontSize: 12, color: T.text4, background: "transparent",
        border: "none", cursor: "pointer", padding: "0 4px",
        borderRadius: 4, lineHeight: 1, flexShrink: 0,
        transition: "color 0.15s",
      }}
      onMouseEnter={(e) => e.currentTarget.style.color = T.text2}
      onMouseLeave={(e) => e.currentTarget.style.color = T.text4}
      title="Dismiss"
    >{"\u2715"}</button>
  );
}

/* Section header with count + clear button */
function SectionHeader({ label, count, color, bg, onClear }) {
  return (
    <div style={{
      padding: "8px 14px",
      borderBottom: `1px solid ${T.border}`,
      display: "flex", alignItems: "center", justifyContent: "space-between",
      background: bg,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{
          fontSize: 11, fontFamily: T.mono, fontWeight: 700,
          color, letterSpacing: "0.08em",
        }}>
          {label}
        </span>
        <span style={{ fontSize: 10, fontFamily: T.mono, color, fontWeight: 600 }}>
          {count}
        </span>
      </div>
      <button
        onClick={onClear}
        style={{
          fontSize: 9, fontFamily: T.font, fontWeight: 600,
          color: T.text4, background: "transparent",
          border: "none", cursor: "pointer", padding: "2px 6px",
          borderRadius: 4, transition: "color 0.15s",
        }}
        onMouseEnter={(e) => e.currentTarget.style.color = T.text2}
        onMouseLeave={(e) => e.currentTarget.style.color = T.text4}
      >
        Clear
      </button>
    </div>
  );
}


export default function NotificationBell() {
  const { address: walletAddress } = useWallet();
  const [events, setEvents] = useState([]);
  const [anomalies, setAnomalies] = useState([]);
  const [warnings, setWarnings] = useState([]);
  const [exhaustionOpps, setExhaustionOpps] = useState([]);
  const [marketSetups, setMarketSetups] = useState([]);
  const [open, setOpen] = useState(false);
  const [dismissed, setDismissedState] = useState(getDismissed);
  const [lastSeen, setLastSeen] = useState(() => {
    const stored = localStorage.getItem("rcce-notif-lastseen");
    return stored ? parseInt(stored, 10) : Math.floor(Date.now() / 1000);
  });
  const panelRef = useRef(null);

  // --- Dismiss helpers ---
  const dismiss = (key) => {
    const next = [...dismissed, key];
    setDismissedState(next);
    saveDismissed(next);
  };

  const dismissMany = (keys) => {
    const next = [...dismissed, ...keys];
    setDismissedState(next);
    saveDismissed(next);
  };

  const clearAll = () => {
    const allKeys = [
      ...anomalies.map(a => `anom:${a.dedup_key}`),
      ...warnings.map(w => `warn:${w.type}:${w.symbol}`),
      ...exhaustionOpps.map(o => `opp:${o.type}:${o.symbol}`),
      ...marketSetups.map(s => `setup:${s.type}:${s.symbol}`),
      ...events.map(e => `ev:${e.event_type}:${e.symbol}:${e.timestamp}`),
    ];
    dismissMany(allKeys);
  };

  const isDismissed = (key) => dismissed.includes(key);

  // --- Data fetching ---
  const fetchNotifs = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/notifications?limit=10`);
      if (!res.ok) return;
      const data = await res.json();
      setEvents(data.events || []);
    } catch (_) {}
  }, []);

  const fetchAnomalies = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/notifications/anomalies`);
      if (!res.ok) return;
      const data = await res.json();
      setAnomalies(data.anomalies || []);
    } catch (_) {}
  }, []);

  const fetchWarnings = useCallback(async () => {
    if (!walletAddress) {
      setWarnings([]);
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/api/notifications/position-warnings?address=${walletAddress}`);
      if (!res.ok) return;
      const data = await res.json();
      setWarnings(data.warnings || []);
    } catch (_) {}
  }, [walletAddress]);

  const fetchExhaustionOpps = useCallback(async () => {
    try {
      const url = walletAddress
        ? `${API_BASE}/api/notifications/exhaustion-opportunities?address=${walletAddress}`
        : `${API_BASE}/api/notifications/exhaustion-opportunities`;
      const res = await fetch(url);
      if (!res.ok) return;
      const data = await res.json();
      setExhaustionOpps(data.opportunities || []);
    } catch (_) {}
  }, [walletAddress]);

  const [setupFilter, setSetupFilter] = useState("HIGH"); // HIGH | MED | ALL

  const fetchMarketSetups = useCallback(async () => {
    try {
      const score = setupFilter === "HIGH" ? 3 : setupFilter === "MED" ? 2 : 0;
      const url = walletAddress
        ? `${API_BASE}/api/notifications/market-setups?address=${walletAddress}&min_score=${score}`
        : `${API_BASE}/api/notifications/market-setups?min_score=${score}`;
      const res = await fetch(url);
      if (!res.ok) return;
      const data = await res.json();
      setMarketSetups(data.setups || []);
    } catch (_) {}
  }, [walletAddress, setupFilter]);

  // Poll every 60s
  useEffect(() => {
    fetchNotifs();
    fetchAnomalies();
    fetchWarnings();
    fetchExhaustionOpps();
    fetchMarketSetups();
    const iv = setInterval(() => {
      fetchNotifs(); fetchAnomalies(); fetchWarnings(); fetchExhaustionOpps(); fetchMarketSetups();
    }, 60_000);
    return () => clearInterval(iv);
  }, [fetchNotifs, fetchAnomalies, fetchWarnings, fetchExhaustionOpps, fetchMarketSetups]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // --- Filtered lists (after dismiss) ---
  const visibleAnomalies = anomalies.filter(a => !isDismissed(`anom:${a.dedup_key}`));
  const visibleWarnings = warnings.filter(w => !isDismissed(`warn:${w.type}:${w.symbol}`));
  const visibleOpps = exhaustionOpps.filter(o => !isDismissed(`opp:${o.type}:${o.symbol}`));
  const visibleSetups = marketSetups.filter(s => !isDismissed(`setup:${s.type}:${s.symbol}`));
  const visibleEvents = events.filter(e => !isDismissed(`ev:${e.event_type}:${e.symbol}:${e.timestamp}`));

  const totalVisible = visibleAnomalies.length + visibleWarnings.length + visibleOpps.length + visibleSetups.length + visibleEvents.length;

  const unseen = visibleEvents.filter((e) => e.timestamp > lastSeen).length;
  const hasAnomalies = visibleAnomalies.length > 0;
  const hasWarnings = visibleWarnings.length > 0;
  const hasCritical = hasAnomalies || visibleWarnings.some(w => w.severity === "critical" || w.severity === "high");
  const hasOpps = visibleOpps.length > 0;
  const hasSetups = visibleSetups.length > 0;
  const hasHighSetup = visibleSetups.some(s => s.severity === "high");

  const markSeen = () => {
    if (events.length > 0) {
      const maxTs = Math.max(...events.map((e) => e.timestamp));
      setLastSeen(maxTs);
      localStorage.setItem("rcce-notif-lastseen", String(maxTs));
    }
  };

  const handleToggle = () => {
    if (!open) {
      markSeen();
    }
    setOpen(!open);
  };

  return (
    <div ref={panelRef} style={{ position: "relative" }}>
      {/* Bell icon */}
      <button
        onClick={handleToggle}
        title="Notifications"
        style={{
          width: 28, height: 28,
          display: "flex", alignItems: "center", justifyContent: "center",
          padding: 0, border: "none", background: "transparent",
          color: hasCritical ? "#f59e0b" : open ? T.accent : T.text3,
          cursor: "pointer", position: "relative",
          transition: "color 0.15s ease",
        }}
        onMouseEnter={(e) => { e.currentTarget.style.color = hasCritical ? "#f59e0b" : T.accent; }}
        onMouseLeave={(e) => { if (!open) e.currentTarget.style.color = hasCritical ? "#f59e0b" : T.text3; }}
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {(unseen > 0 || hasAnomalies || hasWarnings || hasOpps || hasSetups) && (
          <span style={{
            position: "absolute", top: 1, right: 1,
            width: 8, height: 8, borderRadius: "50%",
            background: hasAnomalies ? "#ef4444"
                       : hasCritical ? "#ef4444"
                       : hasWarnings ? "#f59e0b"
                       : hasHighSetup ? "#a78bfa"
                       : hasOpps || hasSetups ? "#34d399"
                       : "#ef4444",
            animation: "livePulse 2s ease-in-out infinite",
          }} />
        )}
      </button>

      {/* Dropdown panel */}
      {open && (
        <div style={{
          position: "fixed", top: 56, right: 10,
          width: 340, maxWidth: "calc(100vw - 20px)", maxHeight: 500,
          background: T.popoverBg,
          border: `1px solid ${T.border}`,
          borderRadius: T.radiusSm,
          boxShadow: T.shadowHeavy,
          zIndex: 9999,
          overflowY: "auto",
        }}>
          {/* Global clear all */}
          {totalVisible > 0 && (
            <div style={{
              padding: "6px 14px",
              borderBottom: `1px solid ${T.border}`,
              display: "flex", alignItems: "center", justifyContent: "flex-end",
              background: "transparent",
            }}>
              <button
                onClick={clearAll}
                style={{
                  fontSize: 9, fontFamily: T.font, fontWeight: 600,
                  color: T.text4, background: "transparent",
                  border: "none", cursor: "pointer", padding: "2px 8px",
                  borderRadius: 4, transition: "color 0.15s",
                }}
                onMouseEnter={(e) => e.currentTarget.style.color = T.text2}
                onMouseLeave={(e) => e.currentTarget.style.color = T.text4}
              >
                Clear all
              </button>
            </div>
          )}

          {/* Anomalies Section */}
          {visibleAnomalies.length > 0 && (
            <>
              <SectionHeader
                label="ANOMALIES"
                count={visibleAnomalies.length}
                color="#ef4444"
                bg="rgba(239, 68, 68, 0.05)"
                onClear={() => dismissMany(anomalies.map(a => `anom:${a.dedup_key}`))}
              />
              {visibleAnomalies.map((a, i) => {
                const color = a.severity === "critical" ? "#ef4444" : "#f59e0b";
                const coin = (a.symbol || "").replace("/USDT", "").replace("/USD", "");
                const typeMap = {
                  EXTREME_FUNDING: "FUNDING",
                  OI_SURGE: "OI",
                  VOLUME_SPIKE: "VOL",
                  LSR_EXTREME: "LSR",
                  CVD_EXTREME: "CVD",
                };
                const key = `anom:${a.dedup_key}`;
                return (
                  <div
                    key={key + "-" + i}
                    style={{
                      padding: "8px 14px",
                      borderBottom: `1px solid ${T.border}`,
                      background: a.severity === "critical" ? "rgba(239, 68, 68, 0.06)" : "transparent",
                    }}
                  >
                    <div style={{
                      display: "flex", alignItems: "center", gap: 8,
                      marginBottom: 3,
                    }}>
                      <span style={{ color, fontSize: 11, lineHeight: 1 }}>{"\u26a0"}</span>
                      <span style={{
                        fontSize: 11, fontFamily: T.mono, fontWeight: 600,
                        color: T.text1,
                      }}>
                        {coin}
                      </span>
                      <span style={{
                        fontSize: 9, fontFamily: T.mono, fontWeight: 700,
                        padding: "1px 5px", borderRadius: 4,
                        background: color + "18", color,
                      }}>
                        {typeMap[a.anomaly_type] || a.anomaly_type}
                      </span>
                      <span style={{
                        fontSize: 9, fontFamily: T.mono, fontWeight: 700,
                        padding: "1px 5px", borderRadius: 4,
                        background: color + "18", color,
                        textTransform: "uppercase",
                      }}>
                        {a.severity}
                      </span>
                      <span style={{ marginLeft: "auto" }} />
                      <DismissBtn onClick={() => dismiss(key)} />
                    </div>
                    <div style={{
                      fontSize: 10, fontFamily: T.mono, color: T.text4,
                      paddingLeft: 19, lineHeight: 1.5,
                    }}>
                      {a.context}
                    </div>
                  </div>
                );
              })}
            </>
          )}

          {/* Position Warnings Section */}
          {visibleWarnings.length > 0 && (
            <>
              <SectionHeader
                label="POSITION ALERTS"
                count={visibleWarnings.length}
                color="#f59e0b"
                bg="rgba(245, 158, 11, 0.05)"
                onClear={() => dismissMany(warnings.map(w => `warn:${w.type}:${w.symbol}`))}
              />
              {visibleWarnings.map((w, i) => {
                const color = SEVERITY_COLORS[w.severity] || T.text3;
                const icon = SEVERITY_ICONS[w.severity] || "\u2022";
                const key = `warn:${w.type}:${w.symbol}`;
                return (
                  <div
                    key={key + "-" + i}
                    style={{
                      padding: "8px 14px",
                      borderBottom: `1px solid ${T.border}`,
                      background: w.severity === "critical" ? "rgba(239, 68, 68, 0.06)" : "transparent",
                    }}
                  >
                    <div style={{
                      display: "flex", alignItems: "center", gap: 8,
                      marginBottom: 3,
                    }}>
                      <span style={{ color, fontSize: 11, lineHeight: 1 }}>{icon}</span>
                      <span style={{
                        fontSize: 11, fontFamily: T.mono, fontWeight: 600,
                        color: T.text1, flex: 1,
                      }}>
                        {w.title}
                      </span>
                      <span style={{
                        fontSize: 9, fontFamily: T.mono, fontWeight: 700,
                        padding: "1px 5px", borderRadius: 4,
                        background: color + "18", color,
                        textTransform: "uppercase",
                      }}>
                        {w.severity}
                      </span>
                      <DismissBtn onClick={() => dismiss(key)} />
                    </div>
                    <div style={{
                      fontSize: 10, fontFamily: T.mono, color: T.text4,
                      paddingLeft: 19, lineHeight: 1.5,
                    }}>
                      {w.detail}
                    </div>
                  </div>
                );
              })}
            </>
          )}

          {/* Exhaustion Opportunities Section */}
          {visibleOpps.length > 0 && (
            <>
              <SectionHeader
                label="EXHAUSTION SETUPS"
                count={visibleOpps.length}
                color="#34d399"
                bg="rgba(52, 211, 153, 0.04)"
                onClear={() => dismissMany(exhaustionOpps.map(o => `opp:${o.type}:${o.symbol}`))}
              />
              {visibleOpps.map((opp, i) => {
                const color = SEVERITY_COLORS[opp.severity] || "#34d399";
                const icon  = opp.type === "exhaustion_floor" ? "\u25c6"   // ◆ confirmed
                            : opp.type === "climax_reversal"  ? "\u26a1"   // ⚡ climax
                            : "\u25aa";                                      // ▪ absorbing
                const key = `opp:${opp.type}:${opp.symbol}`;
                return (
                  <div
                    key={key + "-" + i}
                    style={{
                      padding: "8px 14px",
                      borderBottom: `1px solid ${T.border}`,
                      background: opp.type === "exhaustion_floor" ? "rgba(52,211,153,0.04)" : "transparent",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
                      <span style={{ color, fontSize: 11, lineHeight: 1 }}>{icon}</span>
                      <span style={{ fontSize: 11, fontFamily: T.mono, fontWeight: 600, color: T.text1, flex: 1 }}>
                        {opp.title}
                      </span>
                      <span style={{
                        fontSize: 9, fontFamily: T.mono, fontWeight: 700,
                        padding: "1px 5px", borderRadius: 4,
                        background: color + "18", color,
                        textTransform: "uppercase",
                      }}>
                        {opp.type === "exhaustion_floor" ? "FLOOR" : opp.type === "climax_reversal" ? "CLIMAX" : "EARLY"}
                      </span>
                      <DismissBtn onClick={() => dismiss(key)} />
                    </div>
                    <div style={{ fontSize: 10, fontFamily: T.mono, color: T.text4, paddingLeft: 19, lineHeight: 1.5 }}>
                      {opp.detail}
                    </div>
                  </div>
                );
              })}
            </>
          )}

          {/* OI / Price Divergence — Market Setups */}
          {(visibleSetups.length > 0 || true) && (
            <>
              <div style={{
                padding: "8px 14px",
                borderBottom: `1px solid ${T.border}`,
                display: "flex", alignItems: "center", gap: 8,
                background: "rgba(167,139,250,0.04)",
              }}>
                <span style={{
                  fontSize: 11, fontFamily: T.mono, fontWeight: 700,
                  color: "#a78bfa", letterSpacing: "0.08em", flex: 1,
                }}>
                  MARKET SETUPS
                </span>
                {/* Confluence filter */}
                {["HIGH","MED","ALL"].map(opt => (
                  <button
                    key={opt}
                    onClick={() => setSetupFilter(opt)}
                    style={{
                      padding: "1px 6px", borderRadius: 8,
                      border: `1px solid ${setupFilter === opt ? "#a78bfa" : T.border}`,
                      background: setupFilter === opt ? "rgba(167,139,250,0.15)" : "transparent",
                      color: setupFilter === opt ? "#a78bfa" : T.text4,
                      fontSize: 9, fontFamily: T.mono, fontWeight: 700,
                      cursor: "pointer",
                    }}
                  >
                    {opt === "HIGH" ? "\u2605\u2605\u2605" : opt === "MED" ? "\u2605\u2605" : "ALL"}
                  </button>
                ))}
                <span style={{ fontSize: 10, fontFamily: T.mono, color: "#a78bfa", fontWeight: 600 }}>
                  {visibleSetups.length}
                </span>
                {visibleSetups.length > 0 && (
                  <button
                    onClick={() => dismissMany(marketSetups.map(s => `setup:${s.type}:${s.symbol}`))}
                    style={{
                      fontSize: 9, fontFamily: T.font, fontWeight: 600,
                      color: T.text4, background: "transparent",
                      border: "none", cursor: "pointer", padding: "2px 6px",
                      borderRadius: 4, transition: "color 0.15s",
                    }}
                    onMouseEnter={(e) => e.currentTarget.style.color = T.text2}
                    onMouseLeave={(e) => e.currentTarget.style.color = T.text4}
                  >
                    Clear
                  </button>
                )}
              </div>
              {visibleSetups.length === 0 && (
                <div style={{ padding: "8px 14px", borderBottom: `1px solid ${T.border}` }}>
                  <span style={{ fontSize: 10, fontFamily: T.mono, color: T.text4, fontStyle: "italic" }}>
                    No setups at this threshold
                  </span>
                </div>
              )}
              {visibleSetups.map((s, i) => {
                const SETUP_COLORS = {
                  squeeze_setup:      "#a78bfa",
                  crowded_short_entry:"#34d399",
                  oi_front_run:       "#22d3ee",
                  shorts_into_floor:  "#f59e0b",
                  capitulation_watch: "#6b7280",
                  cvd_bullish_div:    "#34d399",
                  spot_led_breakout:  "#22d3ee",
                };
                const SETUP_ICONS = {
                  squeeze_setup:      "\u{1F300}",  // 🌀
                  crowded_short_entry:"\u{1F525}",  // 🔥
                  oi_front_run:       "\u{1F4C8}",  // 📈
                  shorts_into_floor:  "\u26a1",     // ⚡
                  capitulation_watch: "\u{1F6A8}",  // 🚨
                  cvd_bullish_div:    "\u{1F4CA}",  // 📊
                  spot_led_breakout:  "\u{1F30A}",  // 🌊
                };
                const color = SETUP_COLORS[s.type] || "#a78bfa";
                const icon  = SETUP_ICONS[s.type]  || "\u25c6";
                const SETUP_LABELS = {
                  squeeze_setup:       "SQUEEZE",
                  crowded_short_entry: "SHORT TRAP",
                  oi_front_run:        "OI FRONT-RUN",
                  shorts_into_floor:   "FLOOR",
                  capitulation_watch:  "CAPITULATION",
                  cvd_bullish_div:     "CVD DIV",
                  spot_led_breakout:   "SPOT-LED",
                };
                const key = `setup:${s.type}:${s.symbol}`;
                return (
                  <div
                    key={key + "-" + i}
                    style={{
                      padding: "8px 14px",
                      borderBottom: `1px solid ${T.border}`,
                      background: s.severity === "high" ? color + "06" : "transparent",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
                      <span style={{ color, fontSize: 11, lineHeight: 1 }}>{icon}</span>
                      <span style={{ fontSize: 11, fontFamily: T.mono, fontWeight: 600, color: T.text1, flex: 1 }}>
                        {s.title}
                      </span>
                      {/* Confluence dots */}
                      {s.confluence_score != null && (
                        <span style={{ fontSize: 8, color, opacity: 0.8, letterSpacing: "-1px" }}>
                          {"\u25cf".repeat(s.confluence_score)}{"\u25cb".repeat(7 - (s.confluence_score || 0))}
                        </span>
                      )}
                      <span style={{
                        fontSize: 9, fontFamily: T.mono, fontWeight: 700,
                        padding: "1px 5px", borderRadius: 4,
                        background: color + "18", color,
                        textTransform: "uppercase", whiteSpace: "nowrap",
                      }}>
                        {SETUP_LABELS[s.type] || s.type}
                      </span>
                      <DismissBtn onClick={() => dismiss(key)} />
                    </div>
                    <div style={{ fontSize: 10, fontFamily: T.mono, color: T.text4, paddingLeft: 19, lineHeight: 1.5 }}>
                      {s.detail}
                    </div>
                  </div>
                );
              })}
            </>
          )}

          {/* Signal Events Section */}
          {visibleEvents.length > 0 && (
            <>
              <SectionHeader
                label="SIGNAL EVENTS"
                count={visibleEvents.length}
                color={T.text2}
                bg="transparent"
                onClear={() => dismissMany(events.map(e => `ev:${e.event_type}:${e.symbol}:${e.timestamp}`))}
              />
              {visibleEvents.map((ev, i) => {
                const isSignal = ev.event_type === "signal";
                const color = isSignal
                  ? (TRANSITION_COLORS[ev.transition_type] || T.text3)
                  : T.accent;
                const icon = isSignal
                  ? (TRANSITION_ICONS[ev.transition_type] || "\u2022")
                  : TRANSITION_ICONS.regime;
                const isNew = ev.timestamp > lastSeen;
                const key = `ev:${ev.event_type}:${ev.symbol}:${ev.timestamp}`;

                return (
                  <div
                    key={key + "-" + i}
                    style={{
                      padding: "8px 14px",
                      borderBottom: i < visibleEvents.length - 1 ? `1px solid ${T.border}` : "none",
                      background: isNew ? T.overlay03 : "transparent",
                      transition: "background 0.15s",
                    }}
                  >
                    <div style={{
                      display: "flex", alignItems: "center", gap: 8,
                      marginBottom: 2,
                    }}>
                      <span style={{ color, fontSize: 10, lineHeight: 1 }}>{icon}</span>
                      <span style={{
                        fontSize: 11, fontFamily: T.mono, fontWeight: 600,
                        color: T.text1,
                      }}>
                        {coinName(ev.symbol)}
                      </span>
                      <span style={{
                        fontSize: 10, fontFamily: T.mono, color: T.text4,
                        marginLeft: "auto",
                      }}>
                        {timeAgo(ev.timestamp)}
                      </span>
                      <DismissBtn onClick={() => dismiss(key)} />
                    </div>
                    <div style={{
                      fontSize: 10, fontFamily: T.mono, color: T.text3,
                      paddingLeft: 18,
                    }}>
                      {isSignal ? (
                        <>
                          <span style={{ color: T.text4 }}>{ev.prev_label || "\u2014"}</span>
                          {" \u2192 "}
                          <span style={{ color, fontWeight: 600 }}>{ev.label}</span>
                          {ev.transition_type && (
                            <span style={{
                              marginLeft: 6, fontSize: 9,
                              padding: "1px 5px", borderRadius: 4,
                              background: color + "18",
                              color,
                            }}>
                              {ev.transition_type}
                            </span>
                          )}
                          {ev.win_rate != null && (
                            <span style={{
                              marginLeft: 4, fontSize: 9,
                              padding: "1px 5px", borderRadius: 4,
                              background: ev.win_rate >= 65 ? "#34d39918" : ev.win_rate >= 50 ? "#fbbf2418" : "#f8717118",
                              color: ev.win_rate >= 65 ? "#34d399" : ev.win_rate >= 50 ? "#fbbf24" : "#f87171",
                              fontWeight: 600,
                            }}>
                              {ev.regime_win_rate != null ? ev.regime_win_rate : ev.win_rate}% WR
                            </span>
                          )}
                        </>
                      ) : (
                        <>
                          <span style={{ color: T.text4 }}>{ev.prev_label || "\u2014"}</span>
                          {" \u2192 "}
                          <span style={{ color: T.accent, fontWeight: 600 }}>{ev.label}</span>
                          <span style={{
                            marginLeft: 6, fontSize: 9,
                            padding: "1px 5px", borderRadius: 4,
                            background: T.accentDim,
                            color: T.accent,
                          }}>
                            REGIME
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                );
              })}
            </>
          )}

          {/* Empty state */}
          {totalVisible === 0 && (
            <div style={{
              padding: "40px 14px", textAlign: "center",
              color: T.text4, fontFamily: T.mono, fontSize: 11,
            }}>
              No notifications
            </div>
          )}
        </div>
      )}
    </div>
  );
}
