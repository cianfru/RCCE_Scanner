import { useState, useEffect, useRef, useCallback } from "react";
import { T } from "../theme";
import { useWallet } from "../WalletContext.jsx";
import { useToast } from "./ToastNotifications.jsx";

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

export default function NotificationBell() {
  const { address: walletAddress } = useWallet();
  const { addToast } = useToast();
  const [events, setEvents] = useState([]);
  const [warnings, setWarnings] = useState([]);
  const [exhaustionOpps, setExhaustionOpps] = useState([]);
  const [marketSetups, setMarketSetups] = useState([]);
  const [whaleEvents, setWhaleEvents] = useState([]);
  const [open, setOpen] = useState(false);
  const [lastSeen, setLastSeen] = useState(() => {
    const stored = localStorage.getItem("rcce-notif-lastseen");
    return stored ? parseInt(stored, 10) : Math.floor(Date.now() / 1000);
  });
  const panelRef = useRef(null);
  const lastWhaleTs = useRef(0);
  const lastEventTs = useRef(0);

  const fetchNotifs = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/notifications?limit=15`);
      if (!res.ok) return;
      const data = await res.json();
      const newEvents = data.events || [];
      setEvents(newEvents);

      // Toast for HIGH priority new events
      for (const ev of newEvents) {
        if (ev.priority !== "high") continue;
        if (ev.timestamp <= lastEventTs.current) continue;
        const isEntry = ev.transition_type === "ENTRY" || ev.transition_type === "UPGRADE";
        addToast({
          type: isEntry ? "entry" : "exit",
          title: `${ev.transition_type} ${coinName(ev.symbol || "")}`,
          body: `${ev.prev_label || "WAIT"} \u2192 ${ev.label}`,
          symbol: coinName(ev.symbol || ""),
          severity: ev.priority,
        });
      }
      if (newEvents.length > 0) {
        lastEventTs.current = Math.max(lastEventTs.current, ...newEvents.map(e => e.timestamp || 0));
      }
    } catch (_) {}
  }, [addToast]);

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

  const fetchWhaleEvents = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/hyperlens/follow/events?limit=20`);
      if (!res.ok) return;
      const data = await res.json();
      const newWhaleEvents = data.events || [];
      setWhaleEvents(newWhaleEvents);

      // Toast for new whale trades
      for (const ev of newWhaleEvents) {
        if ((ev.timestamp || 0) <= lastWhaleTs.current) continue;
        const addr = ev.wallet ? `${ev.wallet.slice(0, 6)}...${ev.wallet.slice(-4)}` : "Wallet";
        const action = ev.status === "OPENED" ? "opened" : ev.status === "CLOSED" ? "closed" : "flipped";
        const sizeStr = ev.size_usd >= 1e6 ? `$${(ev.size_usd / 1e6).toFixed(1)}M` : `$${(ev.size_usd / 1e3).toFixed(0)}K`;
        addToast({
          type: "whale",
          title: `${(ev.cohort || "tracked").toUpperCase()} ${action} ${ev.side} ${ev.coin}`,
          body: `${addr} \u00B7 ${sizeStr} \u00B7 ${ev.leverage || 1}x`,
          symbol: ev.coin,
        });
      }
      if (newWhaleEvents.length > 0) {
        lastWhaleTs.current = Math.max(lastWhaleTs.current, ...newWhaleEvents.map(e => e.timestamp || 0));
      }
    } catch (_) {}
  }, [addToast]);

  // Poll every 30s (faster for whale alerts)
  useEffect(() => {
    fetchNotifs();
    fetchWarnings();
    fetchExhaustionOpps();
    fetchMarketSetups();
    fetchWhaleEvents();
    const iv = setInterval(() => {
      fetchNotifs(); fetchWarnings(); fetchExhaustionOpps(); fetchMarketSetups(); fetchWhaleEvents();
    }, 30_000);
    return () => clearInterval(iv);
  }, [fetchNotifs, fetchWarnings, fetchExhaustionOpps, fetchMarketSetups, fetchWhaleEvents]);

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

  const unseen = visibleEvents.filter((e) => e.timestamp > lastSeen).length;
  const hasWarnings = warnings.length > 0;
  const hasCritical = warnings.some(w => w.severity === "critical" || w.severity === "high");
  const hasOpps = exhaustionOpps.length > 0;
  const hasSetups = marketSetups.length > 0;
  const hasHighSetup = marketSetups.some(s => s.severity === "high");
  const hasWhaleEvents = visibleWhale.length > 0;
  const hasAnything = unseen > 0 || hasWarnings || hasOpps || hasSetups || hasWhaleEvents;

  // Dismissed-at timestamp: anything older is hidden
  const [dismissedAt, setDismissedAt] = useState(() => {
    const stored = localStorage.getItem("rcce-notif-dismissed");
    return stored ? parseFloat(stored) : 0;
  });

  const clearAll = () => {
    const now = Math.floor(Date.now() / 1000);
    setDismissedAt(now);
    localStorage.setItem("rcce-notif-dismissed", String(now));
    setLastSeen(now);
    localStorage.setItem("rcce-notif-lastseen", String(now));
  };

  // Filter all sections by dismissedAt
  const visibleEvents = events.filter(e => (e.timestamp || 0) > dismissedAt);
  const visibleWhale = whaleEvents.filter(e => (e.timestamp || 0) > dismissedAt);

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
        {hasAnything && (
          <span style={{
            position: "absolute", top: 1, right: 1,
            width: 8, height: 8, borderRadius: "50%",
            background: hasCritical ? "#ef4444"
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
          display: "flex", flexDirection: "column",
        }}>
          {/* Clear All header */}
          <div style={{
            padding: "8px 14px",
            borderBottom: `1px solid ${T.border}`,
            display: "flex", alignItems: "center", justifyContent: "space-between",
          }}>
            <span style={{ fontSize: 11, fontFamily: T.mono, fontWeight: 700, color: T.text2, letterSpacing: "0.08em" }}>
              NOTIFICATIONS
            </span>
            <button
              onClick={clearAll}
              style={{
                background: "transparent", border: "none", cursor: "pointer",
                fontSize: 10, fontFamily: T.mono, fontWeight: 600,
                color: T.text4, padding: "2px 6px", borderRadius: 4,
                transition: "color 0.15s",
              }}
              onMouseEnter={e => { e.currentTarget.style.color = T.accent; }}
              onMouseLeave={e => { e.currentTarget.style.color = T.text4; }}
            >
              CLEAR ALL
            </button>
          </div>

          {/* Whale Alerts Section */}
          {visibleWhale.length > 0 && (
            <>
              <div style={{
                padding: "10px 14px",
                borderBottom: `1px solid ${T.border}`,
                display: "flex", alignItems: "center", justifyContent: "space-between",
                background: "rgba(192, 132, 252, 0.05)",
              }}>
                <span style={{
                  fontSize: 11, fontFamily: T.mono, fontWeight: 700,
                  color: "#c084fc", letterSpacing: "0.08em",
                }}>
                  WHALE ALERTS
                </span>
                <span style={{
                  fontSize: 10, fontFamily: T.mono, color: "#c084fc",
                  fontWeight: 600,
                }}>{visibleWhale.length}</span>
              </div>
              {visibleWhale.slice(0, 8).map((ev, i) => {
                const addr = ev.wallet ? `${ev.wallet.slice(0, 6)}...${ev.wallet.slice(-4)}` : "?";
                const actionColor = ev.status === "OPENED" ? "#34d399" : ev.status === "CLOSED" ? "#f87171" : "#fbbf24";
                const sizeStr = ev.size_usd >= 1e6 ? `$${(ev.size_usd / 1e6).toFixed(1)}M` : `$${(ev.size_usd / 1e3).toFixed(0)}K`;
                return (
                  <div key={`whale-${i}`} style={{
                    padding: "8px 14px",
                    borderBottom: `1px solid ${T.border}`,
                    display: "flex", flexDirection: "column", gap: 2,
                  }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span style={{
                        fontSize: 9, fontWeight: 700, fontFamily: T.mono,
                        padding: "1px 5px", borderRadius: 4,
                        background: `${actionColor}18`, color: actionColor,
                        border: `1px solid ${actionColor}40`,
                      }}>
                        {ev.status}
                      </span>
                      <span style={{ fontSize: 11, fontFamily: T.mono, fontWeight: 600, color: T.text1 }}>
                        {ev.side} {ev.coin}
                      </span>
                      <span style={{ fontSize: 10, fontFamily: T.mono, color: T.text3, marginLeft: "auto" }}>
                        {sizeStr} {ev.leverage}x
                      </span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 9, fontFamily: T.mono, color: T.text4 }}>
                      <span>{addr}</span>
                      {ev.cohort && (
                        <span style={{
                          padding: "0 4px", borderRadius: 3,
                          background: ev.cohort === "elite" ? "rgba(251,191,36,0.15)" : "rgba(192,132,252,0.15)",
                          color: ev.cohort === "elite" ? "#fbbf24" : "#c084fc",
                          fontWeight: 600, fontSize: 8, letterSpacing: "0.04em",
                        }}>
                          {ev.cohort.toUpperCase()}
                        </span>
                      )}
                      {ev.pnl != null && ev.pnl !== 0 && (
                        <span style={{ color: ev.pnl > 0 ? "#34d399" : "#f87171" }}>
                          {ev.pnl > 0 ? "+" : ""}{ev.pnl >= 1000 ? `$${(ev.pnl / 1000).toFixed(1)}K` : `$${ev.pnl.toFixed(0)}`}
                        </span>
                      )}
                      <span style={{ marginLeft: "auto" }}>
                        {ev.timestamp ? timeAgo(ev.timestamp) : ""}
                      </span>
                    </div>
                  </div>
                );
              })}
            </>
          )}

          {/* Position Warnings Section */}
          {warnings.length > 0 && (
            <>
              <div style={{
                padding: "10px 14px",
                borderBottom: `1px solid ${T.border}`,
                display: "flex", alignItems: "center", justifyContent: "space-between",
                background: "rgba(245, 158, 11, 0.05)",
              }}>
                <span style={{
                  fontSize: 11, fontFamily: T.mono, fontWeight: 700,
                  color: "#f59e0b", letterSpacing: "0.08em",
                }}>
                  POSITION ALERTS
                </span>
                <span style={{
                  fontSize: 10, fontFamily: T.mono, color: "#f59e0b",
                  fontWeight: 600,
                }}>
                  {warnings.length}
                </span>
              </div>
              {warnings.map((w, i) => {
                const color = SEVERITY_COLORS[w.severity] || T.text3;
                const icon = SEVERITY_ICONS[w.severity] || "\u2022";
                return (
                  <div
                    key={`warn-${w.type}-${w.symbol}-${i}`}
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
          {exhaustionOpps.length > 0 && (
            <>
              <div style={{
                padding: "10px 14px",
                borderBottom: `1px solid ${T.border}`,
                display: "flex", alignItems: "center", justifyContent: "space-between",
                background: "rgba(52, 211, 153, 0.04)",
              }}>
                <span style={{
                  fontSize: 11, fontFamily: T.mono, fontWeight: 700,
                  color: "#34d399", letterSpacing: "0.08em",
                }}>
                  EXHAUSTION SETUPS
                </span>
                <span style={{
                  fontSize: 10, fontFamily: T.mono, color: "#34d399", fontWeight: 600,
                }}>
                  {exhaustionOpps.length}
                </span>
              </div>
              {exhaustionOpps.map((opp, i) => {
                const color = SEVERITY_COLORS[opp.severity] || "#34d399";
                const icon  = opp.type === "exhaustion_floor" ? "\u25c6"   // ◆ confirmed
                            : opp.type === "climax_reversal"  ? "\u26a1"   // ⚡ climax
                            : "\u25aa";                                      // ▪ absorbing
                return (
                  <div
                    key={`opp-${opp.type}-${opp.symbol}-${i}`}
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
          {(marketSetups.length > 0 || true) && (
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
                    {opt === "HIGH" ? "★★★" : opt === "MED" ? "★★" : "ALL"}
                  </button>
                ))}
                <span style={{ fontSize: 10, fontFamily: T.mono, color: "#a78bfa", fontWeight: 600 }}>
                  {marketSetups.length}
                </span>
              </div>
              {marketSetups.length === 0 && (
                <div style={{ padding: "8px 14px", borderBottom: `1px solid ${T.border}` }}>
                  <span style={{ fontSize: 10, fontFamily: T.mono, color: T.text4, fontStyle: "italic" }}>
                    No setups at this threshold
                  </span>
                </div>
              )}
              {marketSetups.map((s, i) => {
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
                return (
                  <div
                    key={`setup-${s.type}-${s.symbol}-${i}`}
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
                          {"●".repeat(s.confluence_score)}{"○".repeat(7 - (s.confluence_score || 0))}
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
          <div style={{
            padding: "10px 14px",
            borderBottom: `1px solid ${T.border}`,
            display: "flex", alignItems: "center", justifyContent: "space-between",
          }}>
            <span style={{
              fontSize: 11, fontFamily: T.mono, fontWeight: 600,
              color: T.text2, letterSpacing: "0.08em",
            }}>
              SIGNAL EVENTS
            </span>
            {visibleEvents.length > 0 && (
              <span style={{
                fontSize: 10, fontFamily: T.mono, color: T.text4,
              }}>
                {visibleEvents.length}
              </span>
            )}
          </div>

          {visibleEvents.length === 0 && warnings.length === 0 && visibleWhale.length === 0 ? (
            <div style={{
              padding: "40px 14px", textAlign: "center",
              color: T.text4, fontFamily: T.mono, fontSize: 11,
            }}>
              No new events
            </div>
          ) : (
            visibleEvents.map((ev, i) => {
              const isSignal = ev.event_type === "signal";
              const color = isSignal
                ? (TRANSITION_COLORS[ev.transition_type] || T.text3)
                : T.accent;
              const icon = isSignal
                ? (TRANSITION_ICONS[ev.transition_type] || "\u2022")
                : TRANSITION_ICONS.regime;
              const isNew = ev.timestamp > lastSeen;

              return (
                <div
                  key={`${ev.event_type}-${ev.symbol}-${ev.timestamp}-${i}`}
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
            })
          )}
        </div>
      )}
    </div>
  );
}
