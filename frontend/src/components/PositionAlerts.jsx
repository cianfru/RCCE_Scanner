import { useState, useEffect, useCallback } from "react";
import { T, m } from "../theme.js";
import { useWallet } from "../WalletContext.jsx";
import GlassCard from "./GlassCard.jsx";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const SEVERITY_STYLES = {
  critical: { bg: "rgba(239, 68, 68, 0.08)",   border: "rgba(239, 68, 68, 0.25)",  color: "#ef4444", label: "CRITICAL" },
  high:     { bg: "rgba(245, 158, 11, 0.08)",  border: "rgba(245, 158, 11, 0.25)", color: "#f59e0b", label: "HIGH" },
  medium:   { bg: "rgba(234, 179, 8, 0.06)",   border: "rgba(234, 179, 8, 0.20)",  color: "#eab308", label: "MEDIUM" },
  low:      { bg: "rgba(107, 114, 128, 0.06)", border: "rgba(107, 114, 128, 0.2)", color: "#6b7280", label: "LOW" },
  positive: { bg: "rgba(52, 211, 153, 0.07)",  border: "rgba(52, 211, 153, 0.22)", color: "#34d399", label: "SETUP" },
};

const DISMISSED_KEY = "rcce-dismissed-alerts";

function getDismissed() {
  try {
    const raw = sessionStorage.getItem(DISMISSED_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch { return []; }
}

function setDismissed(list) {
  sessionStorage.setItem(DISMISSED_KEY, JSON.stringify(list));
}

export default function PositionAlerts({ isMobile }) {
  const { address } = useWallet();
  const [warnings, setWarnings] = useState([]);
  const [dismissed, setDismissedState] = useState(getDismissed);

  const fetchWarnings = useCallback(async () => {
    if (!address) { setWarnings([]); return; }
    try {
      const res = await fetch(`${API_BASE}/api/notifications/position-warnings?address=${address}`);
      if (!res.ok) return;
      const data = await res.json();
      setWarnings(data.warnings || []);
    } catch (_) {}
  }, [address]);

  useEffect(() => {
    fetchWarnings();
    const iv = setInterval(fetchWarnings, 60_000);
    return () => clearInterval(iv);
  }, [fetchWarnings]);

  const dismiss = (alertKey) => {
    const next = [...dismissed, alertKey];
    setDismissedState(next);
    setDismissed(next);
  };

  const dismissAll = () => {
    const keys = visible.map(w => `${w.type}:${w.symbol}`);
    const next = [...dismissed, ...keys];
    setDismissedState(next);
    setDismissed(next);
  };

  // Filter out dismissed
  const visible = warnings.filter(w => !dismissed.includes(`${w.type}:${w.symbol}`));

  if (visible.length === 0) return null;

  return (
    <div style={{ marginTop: isMobile ? T.sp2 : T.sp3 }}>
      <GlassCard style={{
        padding: 0,
        overflow: "hidden",
        border: `1px solid ${SEVERITY_STYLES[visible[0]?.severity]?.border || T.border}`,
      }}>
        {/* Header */}
        <div style={{
          padding: isMobile ? "8px 12px" : "8px 16px",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          borderBottom: `1px solid ${T.border}`,
          background: "rgba(245, 158, 11, 0.04)",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{
              fontSize: m(T.textSm, isMobile),
              color: "#f59e0b",
              letterSpacing: "0.1em",
              fontFamily: T.font,
              fontWeight: 700,
              textTransform: "uppercase",
            }}>
              POSITION ALERTS
            </span>
            <span style={{
              fontSize: m(T.textXs, isMobile),
              fontFamily: T.mono,
              fontWeight: 700,
              padding: "2px 6px",
              borderRadius: 4,
              background: "rgba(245, 158, 11, 0.15)",
              color: "#f59e0b",
            }}>
              {visible.length}
            </span>
          </div>
          <button
            onClick={dismissAll}
            style={{
              fontSize: m(T.textXs, isMobile),
              fontFamily: T.font,
              fontWeight: 600,
              color: T.text4,
              background: "transparent",
              border: "none",
              cursor: "pointer",
              padding: "4px 8px",
              borderRadius: 4,
              transition: "color 0.15s",
            }}
            onMouseEnter={(e) => e.currentTarget.style.color = T.text2}
            onMouseLeave={(e) => e.currentTarget.style.color = T.text4}
          >
            Dismiss all
          </button>
        </div>

        {/* Alert items */}
        {visible.map((w, i) => {
          const sev = SEVERITY_STYLES[w.severity] || SEVERITY_STYLES.medium;
          const alertKey = `${w.type}:${w.symbol}`;

          return (
            <div
              key={alertKey + "-" + i}
              style={{
                padding: isMobile ? "10px 12px" : "10px 16px",
                borderBottom: i < visible.length - 1 ? `1px solid ${T.border}` : "none",
                background: sev.bg,
                display: "flex",
                alignItems: "flex-start",
                gap: 10,
              }}
            >
              {/* Severity indicator */}
              <div style={{
                width: 3,
                minHeight: 32,
                borderRadius: 2,
                background: sev.color,
                flexShrink: 0,
                marginTop: 2,
              }} />

              {/* Content */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                  display: "flex", alignItems: "center", gap: 8,
                  marginBottom: 4,
                }}>
                  <span style={{
                    fontSize: m(T.textSm, isMobile),
                    fontFamily: T.mono,
                    fontWeight: 700,
                    color: T.text1,
                  }}>
                    {w.title}
                  </span>
                  <span style={{
                    fontSize: 9,
                    fontFamily: T.mono,
                    fontWeight: 700,
                    padding: "1px 5px",
                    borderRadius: 3,
                    background: sev.color + "18",
                    color: sev.color,
                    flexShrink: 0,
                  }}>
                    {sev.label}
                  </span>
                </div>
                <div style={{
                  fontSize: m(T.textXs, isMobile),
                  fontFamily: T.font,
                  color: T.text3,
                  lineHeight: 1.6,
                }}>
                  {w.detail}
                </div>
              </div>

              {/* Dismiss button */}
              <button
                onClick={() => dismiss(alertKey)}
                style={{
                  fontSize: 14,
                  color: T.text4,
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  padding: "2px 6px",
                  borderRadius: 4,
                  flexShrink: 0,
                  lineHeight: 1,
                  transition: "color 0.15s",
                }}
                onMouseEnter={(e) => e.currentTarget.style.color = T.text2}
                onMouseLeave={(e) => e.currentTarget.style.color = T.text4}
                title="Dismiss"
              >
                {"\u2715"}
              </button>
            </div>
          );
        })}
      </GlassCard>
    </div>
  );
}
