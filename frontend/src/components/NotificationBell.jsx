import { useState, useEffect, useRef, useCallback } from "react";
import { T } from "../theme";

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
  const [events, setEvents] = useState([]);
  const [open, setOpen] = useState(false);
  const [lastSeen, setLastSeen] = useState(() => {
    const stored = localStorage.getItem("rcce-notif-lastseen");
    return stored ? parseInt(stored, 10) : Math.floor(Date.now() / 1000);
  });
  const panelRef = useRef(null);

  const fetchNotifs = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/notifications?limit=30`);
      if (!res.ok) return;
      const data = await res.json();
      setEvents(data.events || []);
    } catch (_) {}
  }, []);

  // Poll every 60s
  useEffect(() => {
    fetchNotifs();
    const iv = setInterval(fetchNotifs, 60_000);
    return () => clearInterval(iv);
  }, [fetchNotifs]);

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

  const unseen = events.filter((e) => e.timestamp > lastSeen).length;

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
          color: open ? T.accent : T.text3,
          cursor: "pointer", position: "relative",
          transition: "color 0.15s ease",
        }}
        onMouseEnter={(e) => { e.currentTarget.style.color = T.accent; }}
        onMouseLeave={(e) => { if (!open) e.currentTarget.style.color = T.text3; }}
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {unseen > 0 && (
          <span style={{
            position: "absolute", top: 1, right: 1,
            width: 8, height: 8, borderRadius: "50%",
            background: "#ef4444",
            animation: "livePulse 2s ease-in-out infinite",
          }} />
        )}
      </button>

      {/* Dropdown panel */}
      {open && (
        <div style={{
          position: "absolute", top: 36, right: 0,
          width: 320, maxHeight: 420,
          background: T.popoverBg,
          border: `1px solid ${T.border}`,
          borderRadius: T.radiusSm,
          boxShadow: T.shadowHeavy,
          zIndex: 9999,
          overflowY: "auto",
        }}>
          {/* Header */}
          <div style={{
            padding: "10px 14px",
            borderBottom: `1px solid ${T.border}`,
            display: "flex", alignItems: "center", justifyContent: "space-between",
          }}>
            <span style={{
              fontSize: 11, fontFamily: T.mono, fontWeight: 600,
              color: T.text2, letterSpacing: "0.08em",
            }}>
              NOTIFICATIONS
            </span>
            {events.length > 0 && (
              <span style={{
                fontSize: 10, fontFamily: T.mono, color: T.text4,
              }}>
                {events.length} events
              </span>
            )}
          </div>

          {/* Events */}
          {events.length === 0 ? (
            <div style={{
              padding: "40px 14px", textAlign: "center",
              color: T.text4, fontFamily: T.mono, fontSize: 11,
            }}>
              No events yet
            </div>
          ) : (
            events.map((ev, i) => {
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
                    borderBottom: i < events.length - 1 ? `1px solid ${T.border}` : "none",
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
                        <span style={{ color: T.text4 }}>{ev.prev_label || "—"}</span>
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
                        <span style={{ color: T.text4 }}>{ev.prev_label || "—"}</span>
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
