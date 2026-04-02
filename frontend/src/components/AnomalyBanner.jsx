import { useState, useEffect, useCallback } from "react";
import { T, m } from "../theme.js";
import GlassCard from "./GlassCard.jsx";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const DISMISSED_KEY = "rcce-dismissed-anomalies";

const SEVERITY_COLORS = {
  critical: { bg: "rgba(239, 68, 68, 0.06)", border: "rgba(239, 68, 68, 0.30)", color: "#ef4444" },
  high:     { bg: "rgba(245, 158, 11, 0.06)", border: "rgba(245, 158, 11, 0.25)", color: "#f59e0b" },
};

const TYPE_LABELS = {
  EXTREME_FUNDING: "FUNDING",
  OI_SURGE:        "OI",
  VOLUME_SPIKE:    "VOLUME",
  LSR_EXTREME:     "LSR",
  CVD_EXTREME:     "CVD",
};

function getDismissed() {
  try {
    const raw = sessionStorage.getItem(DISMISSED_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch { return []; }
}

function setDismissed(list) {
  sessionStorage.setItem(DISMISSED_KEY, JSON.stringify(list));
}

export default function AnomalyBanner({ isMobile }) {
  const [anomalies, setAnomalies] = useState([]);
  const [dismissed, setDismissedState] = useState(getDismissed);

  const fetchAnomalies = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/notifications/anomalies`);
      if (!res.ok) return;
      const data = await res.json();
      setAnomalies(data.anomalies || []);
    } catch (_) {}
  }, []);

  useEffect(() => {
    fetchAnomalies();
    const iv = setInterval(fetchAnomalies, 60_000);
    return () => clearInterval(iv);
  }, [fetchAnomalies]);

  const dismiss = (key) => {
    const next = [...dismissed, key];
    setDismissedState(next);
    setDismissed(next);
  };

  const dismissAll = () => {
    const keys = visible.map(a => a.dedup_key);
    const next = [...dismissed, ...keys];
    setDismissedState(next);
    setDismissed(next);
  };

  const visible = anomalies.filter(a => !dismissed.includes(a.dedup_key));

  if (visible.length === 0) return null;

  const topSev = visible[0]?.severity || "high";
  const accent = SEVERITY_COLORS[topSev] || SEVERITY_COLORS.high;

  return (
    <div style={{ marginTop: isMobile ? T.sp2 : T.sp3 }}>
      <GlassCard style={{
        padding: 0,
        overflow: "hidden",
        border: `1px solid ${accent.border}`,
      }}>
        {/* Header */}
        <div style={{
          padding: isMobile ? "8px 12px" : "8px 16px",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          borderBottom: `1px solid ${T.border}`,
          background: accent.bg,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {/* Pulsing dot */}
            <span style={{
              width: 8, height: 8,
              borderRadius: "50%",
              background: accent.color,
              display: "inline-block",
              animation: "anomalyPulse 1.5s ease-in-out infinite",
            }} />
            <span style={{
              fontSize: m(T.textSm, isMobile),
              color: accent.color,
              letterSpacing: "0.1em",
              fontFamily: T.font,
              fontWeight: 700,
              textTransform: "uppercase",
            }}>
              ANOMALY DETECTED
            </span>
            <span style={{
              fontSize: m(T.textXs, isMobile),
              fontFamily: T.mono,
              fontWeight: 700,
              padding: "2px 6px",
              borderRadius: 4,
              background: accent.color + "18",
              color: accent.color,
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

        {/* Anomaly rows */}
        {visible.map((a, i) => {
          const sev = SEVERITY_COLORS[a.severity] || SEVERITY_COLORS.high;
          const typeLabel = TYPE_LABELS[a.anomaly_type] || a.anomaly_type;
          const coin = a.symbol?.split("/")[0] || a.symbol;
          const zAbs = Math.abs(a.z_score || 0);
          const barWidth = Math.min(zAbs / 10, 1) * 100;
          const exCount = (a.exchanges_confirmed || []).length;
          const exLabel = exCount >= 2
            ? (a.exchanges_confirmed || []).map(e => e === "hyperliquid" ? "HL" : e === "binance" ? "BN" : e.slice(0,2).toUpperCase()).join("+")
            : exCount === 1
              ? (a.exchanges_confirmed[0] === "hyperliquid" ? "HL" : "BN") + " only"
              : null;

          return (
            <div
              key={a.dedup_key + "-" + i}
              style={{
                padding: isMobile ? "10px 12px" : "10px 16px",
                borderBottom: i < visible.length - 1 ? `1px solid ${T.border}` : "none",
                background: sev.bg,
                display: "flex",
                alignItems: "center",
                gap: 10,
              }}
            >
              {/* Severity bar */}
              <div style={{
                width: 3, minHeight: 28, borderRadius: 2,
                background: sev.color, flexShrink: 0,
              }} />

              {/* Symbol */}
              <span style={{
                fontSize: m(T.textSm, isMobile),
                fontFamily: T.mono,
                fontWeight: 700,
                color: T.text1,
                minWidth: isMobile ? 48 : 64,
              }}>
                {coin}
              </span>

              {/* Type badge */}
              <span style={{
                fontSize: 9,
                fontFamily: T.mono,
                fontWeight: 700,
                padding: "2px 6px",
                borderRadius: 3,
                background: sev.color + "18",
                color: sev.color,
                flexShrink: 0,
                letterSpacing: "0.05em",
              }}>
                {typeLabel}
              </span>

              {/* Exchange confirmation badge */}
              {exLabel && (
                <span style={{
                  fontSize: 8,
                  fontFamily: T.mono,
                  fontWeight: 700,
                  padding: "2px 5px",
                  borderRadius: 3,
                  background: exCount >= 2 ? "rgba(34, 197, 94, 0.12)" : "rgba(107, 114, 128, 0.12)",
                  color: exCount >= 2 ? "#22c55e" : "#6b7280",
                  flexShrink: 0,
                  letterSpacing: "0.03em",
                }}>
                  {exLabel}
                </span>
              )}

              {/* Context */}
              <span style={{
                fontSize: m(T.textXs, isMobile),
                fontFamily: T.font,
                color: T.text3,
                flex: 1,
                minWidth: 0,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}>
                {a.context}
              </span>

              {/* Z-score intensity bar */}
              {!isMobile && (
                <div style={{
                  width: 48, height: 4, borderRadius: 2,
                  background: "rgba(255,255,255,0.06)",
                  flexShrink: 0,
                  overflow: "hidden",
                }} title={`z=${a.z_score}`}>
                  <div style={{
                    width: `${barWidth}%`,
                    height: "100%",
                    borderRadius: 2,
                    background: sev.color,
                    transition: "width 0.3s ease",
                  }} />
                </div>
              )}

              {/* Dismiss */}
              <button
                onClick={() => dismiss(a.dedup_key)}
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

      {/* Pulse animation */}
      <style>{`
        @keyframes anomalyPulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
      `}</style>
    </div>
  );
}
