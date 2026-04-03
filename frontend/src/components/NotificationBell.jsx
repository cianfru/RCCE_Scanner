import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
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
  positive: "\u25b2",  // ▲
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

/* Dismiss button (X) */
function DismissBtn({ onClick }) {
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      style={{
        fontSize: T.textSm, color: T.text4, background: "transparent",
        border: "none", cursor: "pointer", padding: "2px 6px",
        borderRadius: 4, lineHeight: 1, flexShrink: 0,
        transition: "color 0.15s",
      }}
      onMouseEnter={(e) => e.currentTarget.style.color = T.text2}
      onMouseLeave={(e) => e.currentTarget.style.color = T.text4}
      title="Dismiss"
    >{"\u2715"}</button>
  );
}

/* Section header */
function SectionHeader({ label, count, color, bg, onClear }) {
  return (
    <div style={{
      padding: "10px 16px",
      borderBottom: `1px solid ${T.border}`,
      display: "flex", alignItems: "center", justifyContent: "space-between",
      background: bg,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{
          fontSize: T.textSm, fontFamily: T.mono, fontWeight: 700,
          color, letterSpacing: "0.08em",
        }}>
          {label}
        </span>
        <span style={{ fontSize: T.textXs, fontFamily: T.mono, color, fontWeight: 600 }}>
          {count}
        </span>
      </div>
      <button
        onClick={onClear}
        style={{
          fontSize: T.textXs, fontFamily: T.mono, fontWeight: 600,
          color: T.text4, background: "transparent",
          border: "none", cursor: "pointer", padding: "3px 8px",
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

/* Notification card row */
function CardRow({ icon, iconColor, title, badge, badgeColor, detail, onDismiss, bg, children, onClickTitle }) {
  return (
    <div style={{
      padding: "12px 16px",
      borderBottom: `1px solid ${T.border}`,
      background: bg || "transparent",
    }}>
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        marginBottom: 4,
      }}>
        <span style={{ color: iconColor, fontSize: T.textSm, lineHeight: 1 }}>{icon}</span>
        <span
          onClick={onClickTitle}
          style={{
            fontSize: T.textBase, fontFamily: T.mono, fontWeight: 600,
            color: T.text1, flex: 1,
            cursor: onClickTitle ? "pointer" : "default",
            transition: onClickTitle ? "color 0.15s" : "none",
          }}
          onMouseEnter={onClickTitle ? (e) => e.currentTarget.style.color = T.accent : undefined}
          onMouseLeave={onClickTitle ? (e) => e.currentTarget.style.color = T.text1 : undefined}
        >
          {title}
        </span>
        {children}
        {badge && (
          <span style={{
            fontSize: T.textXs, fontFamily: T.mono, fontWeight: 700,
            padding: "2px 7px", borderRadius: 4,
            background: (badgeColor || iconColor) + "18",
            color: badgeColor || iconColor,
            textTransform: "uppercase", whiteSpace: "nowrap",
          }}>
            {badge}
          </span>
        )}
        <DismissBtn onClick={onDismiss} />
      </div>
      {detail && (
        <div style={{
          fontSize: T.textSm, fontFamily: T.mono, color: T.text4,
          paddingLeft: 22, lineHeight: 1.6,
        }}>
          {detail}
        </div>
      )}
    </div>
  );
}


export default function NotificationBell() {
  const navigate = useNavigate();
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

  const [setupFilter, setSetupFilter] = useState("HIGH");

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

  // --- Filtered lists ---
  const visibleAnomalies = anomalies.filter(a => !isDismissed(`anom:${a.dedup_key}`));
  const visibleWarnings = warnings.filter(w => !isDismissed(`warn:${w.type}:${w.symbol}`));
  const visibleOpps = exhaustionOpps.filter(o => !isDismissed(`opp:${o.type}:${o.symbol}`));
  const visibleSetups = marketSetups.filter(s => !isDismissed(`setup:${s.type}:${s.symbol}`));
  const visibleEvents = events.filter(e => !isDismissed(`ev:${e.event_type}:${e.symbol}:${e.timestamp}`));

  const totalVisible = visibleAnomalies.length + visibleWarnings.length + visibleOpps.length + visibleSetups.length + visibleEvents.length;

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
    if (!open) markSeen();
    setOpen(!open);
  };

  const goToCoin = (symbol) => {
    const coin = (symbol || "").replace("/USDT", "").replace("/USD", "");
    if (coin) {
      setOpen(false);
      navigate(`/scanner/${coin}`);
    }
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
        {(hasAnomalies || hasWarnings || hasOpps || hasSetups || visibleEvents.length > 0) && (
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
          width: 420, maxWidth: "calc(100vw - 20px)", maxHeight: "70vh",
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
              padding: "8px 16px",
              borderBottom: `1px solid ${T.border}`,
              display: "flex", alignItems: "center", justifyContent: "flex-end",
            }}>
              <button
                onClick={clearAll}
                style={{
                  fontSize: T.textXs, fontFamily: T.mono, fontWeight: 600,
                  color: T.text4, background: "transparent",
                  border: "none", cursor: "pointer", padding: "3px 8px",
                  borderRadius: 4, transition: "color 0.15s",
                }}
                onMouseEnter={(e) => e.currentTarget.style.color = T.text2}
                onMouseLeave={(e) => e.currentTarget.style.color = T.text4}
              >
                Clear all
              </button>
            </div>
          )}

          {/* Anomalies */}
          {visibleAnomalies.length > 0 && (
            <>
              <SectionHeader
                label="ANOMALIES" count={visibleAnomalies.length}
                color="#ef4444" bg="rgba(239, 68, 68, 0.05)"
                onClear={() => dismissMany(anomalies.map(a => `anom:${a.dedup_key}`))}
              />
              {visibleAnomalies.map((a, i) => {
                const color = a.severity === "critical" ? "#ef4444" : "#f59e0b";
                const coin = coinName(a.symbol || "");
                const typeMap = {
                  EXTREME_FUNDING: "FUNDING", OI_SURGE: "OI",
                  VOLUME_SPIKE: "VOL", LSR_EXTREME: "LSR", CVD_EXTREME: "CVD",
                };
                const key = `anom:${a.dedup_key}`;
                return (
                  <CardRow
                    key={key + "-" + i}
                    icon={"\u26a0"} iconColor={color}
                    title={coin}
                    onClickTitle={() => goToCoin(a.symbol)}
                    badge={typeMap[a.anomaly_type] || a.anomaly_type}
                    badgeColor={color}
                    detail={a.context}
                    onDismiss={() => dismiss(key)}
                    bg={a.severity === "critical" ? "rgba(239, 68, 68, 0.06)" : undefined}
                  >
                    <span style={{
                      fontSize: T.textXs, fontFamily: T.mono, fontWeight: 700,
                      padding: "2px 7px", borderRadius: 4,
                      background: color + "18", color,
                      textTransform: "uppercase",
                    }}>
                      {a.severity}
                    </span>
                  </CardRow>
                );
              })}
            </>
          )}

          {/* Position Warnings */}
          {visibleWarnings.length > 0 && (
            <>
              <SectionHeader
                label="POSITION ALERTS" count={visibleWarnings.length}
                color="#f59e0b" bg="rgba(245, 158, 11, 0.05)"
                onClear={() => dismissMany(warnings.map(w => `warn:${w.type}:${w.symbol}`))}
              />
              {visibleWarnings.map((w, i) => {
                const color = SEVERITY_COLORS[w.severity] || T.text3;
                const icon = SEVERITY_ICONS[w.severity] || "\u2022";
                const key = `warn:${w.type}:${w.symbol}`;
                return (
                  <CardRow
                    key={key + "-" + i}
                    icon={icon} iconColor={color}
                    title={w.title}
                    onClickTitle={() => goToCoin(w.symbol)}
                    badge={w.severity} badgeColor={color}
                    detail={w.detail}
                    onDismiss={() => dismiss(key)}
                    bg={w.severity === "critical" ? "rgba(239, 68, 68, 0.06)" : undefined}
                  />
                );
              })}
            </>
          )}

          {/* Exhaustion Opportunities */}
          {visibleOpps.length > 0 && (
            <>
              <SectionHeader
                label="EXHAUSTION SETUPS" count={visibleOpps.length}
                color="#34d399" bg="rgba(52, 211, 153, 0.04)"
                onClear={() => dismissMany(exhaustionOpps.map(o => `opp:${o.type}:${o.symbol}`))}
              />
              {visibleOpps.map((opp, i) => {
                const color = SEVERITY_COLORS[opp.severity] || "#34d399";
                const icon = opp.type === "exhaustion_floor" ? "\u25c6"
                           : opp.type === "climax_reversal" ? "\u26a1" : "\u25aa";
                const badge = opp.type === "exhaustion_floor" ? "FLOOR"
                            : opp.type === "climax_reversal" ? "CLIMAX" : "EARLY";
                const key = `opp:${opp.type}:${opp.symbol}`;
                return (
                  <CardRow
                    key={key + "-" + i}
                    icon={icon} iconColor={color}
                    title={opp.title}
                    onClickTitle={() => goToCoin(opp.symbol)}
                    badge={badge} badgeColor={color}
                    detail={opp.detail}
                    onDismiss={() => dismiss(key)}
                    bg={opp.type === "exhaustion_floor" ? "rgba(52,211,153,0.04)" : undefined}
                  />
                );
              })}
            </>
          )}

          {/* Market Setups */}
          {(visibleSetups.length > 0 || true) && (
            <>
              <div style={{
                padding: "10px 16px",
                borderBottom: `1px solid ${T.border}`,
                display: "flex", alignItems: "center", gap: 8,
                background: "rgba(167,139,250,0.04)",
              }}>
                <span style={{
                  fontSize: T.textSm, fontFamily: T.mono, fontWeight: 700,
                  color: "#a78bfa", letterSpacing: "0.08em", flex: 1,
                }}>
                  MARKET SETUPS
                </span>
                {["HIGH","MED","ALL"].map(opt => (
                  <button
                    key={opt}
                    onClick={() => setSetupFilter(opt)}
                    style={{
                      padding: "2px 8px", borderRadius: 8,
                      border: `1px solid ${setupFilter === opt ? "#a78bfa" : T.border}`,
                      background: setupFilter === opt ? "rgba(167,139,250,0.15)" : "transparent",
                      color: setupFilter === opt ? "#a78bfa" : T.text4,
                      fontSize: T.textXs, fontFamily: T.mono, fontWeight: 700,
                      cursor: "pointer",
                    }}
                  >
                    {opt === "HIGH" ? "\u2605\u2605\u2605" : opt === "MED" ? "\u2605\u2605" : "ALL"}
                  </button>
                ))}
                <span style={{ fontSize: T.textXs, fontFamily: T.mono, color: "#a78bfa", fontWeight: 600 }}>
                  {visibleSetups.length}
                </span>
                {visibleSetups.length > 0 && (
                  <button
                    onClick={() => dismissMany(marketSetups.map(s => `setup:${s.type}:${s.symbol}`))}
                    style={{
                      fontSize: T.textXs, fontFamily: T.mono, fontWeight: 600,
                      color: T.text4, background: "transparent",
                      border: "none", cursor: "pointer", padding: "3px 8px",
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
                <div style={{ padding: "12px 16px", borderBottom: `1px solid ${T.border}` }}>
                  <span style={{ fontSize: T.textSm, fontFamily: T.mono, color: T.text4, fontStyle: "italic" }}>
                    No setups at this threshold
                  </span>
                </div>
              )}
              {visibleSetups.map((s, i) => {
                const SETUP_COLORS = {
                  squeeze_setup: "#a78bfa", crowded_short_entry: "#34d399",
                  oi_front_run: "#22d3ee", shorts_into_floor: "#f59e0b",
                  capitulation_watch: "#6b7280", cvd_bullish_div: "#34d399",
                  spot_led_breakout: "#22d3ee",
                };
                const SETUP_ICONS = {
                  squeeze_setup: "\u{1F300}", crowded_short_entry: "\u{1F525}",
                  oi_front_run: "\u{1F4C8}", shorts_into_floor: "\u26a1",
                  capitulation_watch: "\u{1F6A8}", cvd_bullish_div: "\u{1F4CA}",
                  spot_led_breakout: "\u{1F30A}",
                };
                const SETUP_LABELS = {
                  squeeze_setup: "SQUEEZE", crowded_short_entry: "SHORT TRAP",
                  oi_front_run: "OI FRONT-RUN", shorts_into_floor: "FLOOR",
                  capitulation_watch: "CAPITULATION", cvd_bullish_div: "CVD DIV",
                  spot_led_breakout: "SPOT-LED",
                };
                const color = SETUP_COLORS[s.type] || "#a78bfa";
                const icon = SETUP_ICONS[s.type] || "\u25c6";
                const key = `setup:${s.type}:${s.symbol}`;
                return (
                  <CardRow
                    key={key + "-" + i}
                    icon={icon} iconColor={color}
                    title={s.title}
                    onClickTitle={() => goToCoin(s.symbol)}
                    badge={SETUP_LABELS[s.type] || s.type} badgeColor={color}
                    detail={s.detail}
                    onDismiss={() => dismiss(key)}
                    bg={s.severity === "high" ? color + "06" : undefined}
                  >
                    {s.confluence_score != null && (
                      <span style={{ fontSize: T.textXs, color, opacity: 0.8, letterSpacing: "-1px" }}>
                        {"\u25cf".repeat(s.confluence_score)}{"\u25cb".repeat(7 - (s.confluence_score || 0))}
                      </span>
                    )}
                  </CardRow>
                );
              })}
            </>
          )}

          {/* Signal Events */}
          {visibleEvents.length > 0 && (
            <>
              <SectionHeader
                label="SIGNAL EVENTS" count={visibleEvents.length}
                color={T.text2} bg="transparent"
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
                      padding: "12px 16px",
                      borderBottom: i < visibleEvents.length - 1 ? `1px solid ${T.border}` : "none",
                      background: isNew ? T.overlay03 : "transparent",
                      transition: "background 0.15s",
                    }}
                  >
                    <div style={{
                      display: "flex", alignItems: "center", gap: 8,
                      marginBottom: 4,
                    }}>
                      <span style={{ color, fontSize: T.textSm, lineHeight: 1 }}>{icon}</span>
                      <span
                        onClick={() => goToCoin(ev.symbol)}
                        style={{
                          fontSize: T.textBase, fontFamily: T.mono, fontWeight: 600,
                          color: T.text1, cursor: "pointer", transition: "color 0.15s",
                        }}
                        onMouseEnter={(e) => e.currentTarget.style.color = T.accent}
                        onMouseLeave={(e) => e.currentTarget.style.color = T.text1}
                      >
                        {coinName(ev.symbol)}
                      </span>
                      <span style={{
                        fontSize: T.textXs, fontFamily: T.mono, color: T.text4,
                        marginLeft: "auto",
                      }}>
                        {timeAgo(ev.timestamp)}
                      </span>
                      <DismissBtn onClick={() => dismiss(key)} />
                    </div>
                    <div style={{
                      fontSize: T.textSm, fontFamily: T.mono, color: T.text3,
                      paddingLeft: 22,
                    }}>
                      {isSignal ? (
                        <>
                          <span style={{ color: T.text4 }}>{ev.prev_label || "\u2014"}</span>
                          {" \u2192 "}
                          <span style={{ color, fontWeight: 600 }}>{ev.label}</span>
                          {ev.transition_type && (
                            <span style={{
                              marginLeft: 6, fontSize: T.textXs,
                              padding: "2px 7px", borderRadius: 4,
                              background: color + "18", color,
                            }}>
                              {ev.transition_type}
                            </span>
                          )}
                          {ev.win_rate != null && (
                            <span style={{
                              marginLeft: 4, fontSize: T.textXs,
                              padding: "2px 7px", borderRadius: 4,
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
                            marginLeft: 6, fontSize: T.textXs,
                            padding: "2px 7px", borderRadius: 4,
                            background: T.accentDim, color: T.accent,
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
              padding: "48px 16px", textAlign: "center",
              color: T.text4, fontFamily: T.mono, fontSize: T.textSm,
            }}>
              No notifications
            </div>
          )}
        </div>
      )}
    </div>
  );
}
