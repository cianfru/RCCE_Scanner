/**
 * SettingsDropdown — runtime feature toggles + presets.
 *
 * Renders a gear icon in the header. Click → popover with:
 *   - Three preset buttons (Idle / Normal / Power)
 *   - Per-feature toggle switches
 *
 * Reads/writes /api/admin/features. Toggles persist on disk and take
 * effect within ~30s without redeploy. Designed for the user's flow:
 *   - "Idle" when not actively trading (only core scanner runs)
 *   - "Normal" sentiment-mode default
 *   - "Power" HyperLens, on-chain tracker and monitor (order-book polling stays off: no page shows it)
 */
import { useState, useEffect, useRef } from "react";
import { T } from "../theme.js";
import Tabs from "./Tabs.jsx";

import { getAdminKey, setAdminKey } from "../auth.js";
const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// Display metadata for each flag — order = display order in the panel.
const FLAG_META = [
  {
    key: "hyperlens_enabled",
    label: "HyperLens",
    desc: "Hyperliquid trader positioning",
  },
  {
    key: "whale_tracker",
    label: "On-chain Transfer Tracker",
    desc: "Etherscan/BSCscan/Solscan polling every 2 min",
  },
  {
    key: "market_monitor",
    label: "Market Monitor",
    desc: "Diff scanner state every 5 min, push WebSocket insights",
  },
];

const PRESETS = [
  {
    key: "idle",
    label: "Idle",
    desc: "Scanner only — auxiliaries off",
  },
  {
    key: "normal",
    label: "Normal",
    desc: "Sentiment mode (default)",
  },
  {
    key: "power",
    label: "Power",
    desc: "Everything on",
  },
];

// Flat text on/off control: no pill switch.
function ToggleSwitch({ checked, onChange, color = T.accent }) {
  return (
    <button
      type="button"
      onClick={onChange}
      aria-pressed={checked}
      style={{
        border: "none", background: "transparent", padding: 0,
        cursor: "pointer", flexShrink: 0, minWidth: 24, textAlign: "right",
        fontSize: 12, fontFamily: T.font, fontWeight: 600,
        color: checked ? color : T.text4,
      }}
    >
      {checked ? "On" : "Off"}
    </button>
  );
}

export default function SettingsDropdown() {
  const [open, setOpen] = useState(false);
  const [flags, setFlags] = useState(null);
  const [activity, setActivity] = useState(null);
  const [busy, setBusy] = useState(false);
  const popoverRef = useRef(null);
  const buttonRef = useRef(null);

  // Load on first open
  useEffect(() => {
    if (open && flags === null) {
      fetch(`${API_BASE}/api/admin/features`)
        .then(r => r.ok ? r.json() : null)
        .then(j => {
          if (j?.flags) setFlags(j.flags);
          if (j?.activity) setActivity(j.activity);
        })
        .catch(() => {});
    }
  }, [open, flags]);

  // Live activity badge — poll while the panel is open. This endpoint is
  // excluded from activity tracking, so polling it never keeps the app awake.
  useEffect(() => {
    if (!open) return;
    let alive = true;
    const tick = () => {
      fetch(`${API_BASE}/api/admin/activity`)
        .then(r => r.ok ? r.json() : null)
        .then(j => { if (alive && j) setActivity(j); })
        .catch(() => {});
    };
    tick();
    const id = setInterval(tick, 5000);
    return () => { alive = false; clearInterval(id); };
  }, [open]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const onDown = (e) => {
      if (popoverRef.current?.contains(e.target)) return;
      if (buttonRef.current?.contains(e.target)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const updateFlag = async (key, value) => {
    if (busy) return;
    setBusy(true);
    // Optimistic update
    setFlags(prev => ({ ...(prev || {}), [key]: value }));
    try {
      const res = await fetch(`${API_BASE}/api/admin/features`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ flags: { [key]: value } }),
      });
      if (res.ok) {
        const j = await res.json();
        if (j.flags) setFlags(j.flags);
      }
    } catch {
      // Revert on error
      setFlags(prev => ({ ...(prev || {}), [key]: !value }));
    } finally {
      setBusy(false);
    }
  };

  const applyPreset = async (preset) => {
    if (busy) return;
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/admin/features`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preset }),
      });
      if (res.ok) {
        const j = await res.json();
        if (j.flags) setFlags(j.flags);
      }
    } finally {
      setBusy(false);
    }
  };

  // Determine which preset (if any) currently matches
  const activePreset = (() => {
    if (!flags) return null;
    const match = (preset) => {
      // Match if flags align with the preset definition
      const presets = {
        idle:   { hyperlens_enabled: false, hyperlens_pressure_map: false, whale_tracker: false, market_monitor: false },
        normal: { hyperlens_enabled: true,  hyperlens_pressure_map: false, whale_tracker: false, market_monitor: false },
        power:  { hyperlens_enabled: true,  hyperlens_pressure_map: false, whale_tracker: true,  market_monitor: true },
      };
      const target = presets[preset];
      if (!target) return false;
      return Object.entries(target).every(([k, v]) => flags[k] === v);
    };
    return PRESETS.find(p => match(p.key))?.key || null;
  })();

  return (
    <div style={{ position: "relative" }}>
      <button
        ref={buttonRef}
        onClick={() => setOpen(o => !o)}
        title="Settings"
        style={{
          width: 30, height: 30,
          padding: 0,
          display: "flex", alignItems: "center", justifyContent: "center",
          background: open ? T.overlay06 : "transparent",
          border: `1px solid ${open ? T.accent : T.border}`,
          borderRadius: 8,
          color: open ? T.accent : T.text3,
          cursor: "pointer",
          transition: "all 0.15s",
        }}
        onMouseEnter={e => { if (!open) e.currentTarget.style.color = T.text1; }}
        onMouseLeave={e => { if (!open) e.currentTarget.style.color = T.text3; }}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      </button>

      {open && (
        <div
          ref={popoverRef}
          style={{
            position: "absolute",
            top: "calc(100% + 8px)",
            right: 0,
            width: 320,
            background: T.popoverBg,
            backdropFilter: "blur(20px) saturate(1.3)",
            WebkitBackdropFilter: "blur(20px) saturate(1.3)",
            border: `1px solid ${T.border}`,
            borderRadius: 12,
            boxShadow: "0 12px 40px rgba(0,0,0,0.6)",
            zIndex: 100,
            padding: 14,
          }}
        >
          {/* Header */}
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            marginBottom: 10, paddingBottom: 8,
            borderBottom: `1px solid ${T.overlay06}`,
          }}>
            <span style={{
              fontSize: T.textSm, color: T.text2, fontFamily: T.font,
              fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase",
            }}>
              Runtime Settings
            </span>
            {flags === null && (
              <span style={{ fontSize: T.textXs, color: T.text4, fontFamily: T.mono }}>
                loading…
              </span>
            )}
          </div>

          {/* Admin key: needed for changes once REFLEX_ADMIN_KEY is set on the server */}
          <label style={{ display: "block", marginBottom: 14 }}>
            <span style={{ display: "block", fontSize: 12, color: T.text3, fontFamily: T.font, marginBottom: 6 }}>
              Admin key <span style={{ color: T.text4 }}>(for changes; stored in this browser only)</span>
            </span>
            <input type="password" autoComplete="off" defaultValue={getAdminKey()} placeholder="Not set"
              onChange={e => setAdminKey(e.target.value)}
              style={{ width: "100%", boxSizing: "border-box", height: 34, padding: "0 10px", borderRadius: 6,
                border: `1px solid ${T.border}`, background: T.overlay04, color: T.text1, fontFamily: T.mono, fontSize: 12 }} />
          </label>

          {/* Power state — active/idle throttle */}
          <div style={{ marginBottom: 14 }}>
            <div style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              marginBottom: 6,
            }}>
              <span style={{
                fontSize: T.textXs, color: T.text4, fontFamily: T.mono,
                fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase",
              }}>
                Power State
              </span>
              {activity && (() => {
                const isActive = !!activity.active;
                const color = isActive ? T.green : T.text4;
                const label = isActive ? "ACTIVE" : "IDLE";
                return (
                  <span style={{
                    display: "inline-flex", alignItems: "center", gap: 5,
                    fontSize: T.textXs, fontFamily: T.mono, fontWeight: 700,
                    letterSpacing: "0.06em", color,
                  }}>
                    <span style={{
                      width: 7, height: 7, borderRadius: "50%",
                      background: color,
                      boxShadow: isActive ? `0 0 6px ${color}` : "none",
                    }} />
                    {label}
                  </span>
                );
              })()}
            </div>
            <div style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              padding: "8px 10px",
              borderRadius: 8,
              background: T.overlay02,
              border: `1px solid ${T.overlay06}`,
              gap: 10,
            }}>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{
                  fontSize: T.textSm, color: T.text1,
                  fontFamily: T.font, fontWeight: 600, marginBottom: 2,
                }}>
                  Keep Awake
                </div>
                <div style={{
                  fontSize: T.textXs, color: T.text4, fontFamily: T.font, lineHeight: 1.35,
                }}>
                  Pin full-speed scanning on. Off: auto-idle when no dashboard is open (wakes instantly on reload).
                </div>
              </div>
              <ToggleSwitch
                checked={flags?.keep_active ?? false}
                color={T.green}
                onChange={() => updateFlag("keep_active", !(flags?.keep_active ?? false))}
              />
            </div>
          </div>

          {/* Presets */}
          <div style={{ marginBottom: 14 }}>
            <div style={{
              fontSize: T.textXs, color: T.text4, fontFamily: T.mono,
              fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase",
              marginBottom: 2,
            }}>
              Presets
            </div>
            <div style={{ opacity: flags === null ? 0.5 : 1, pointerEvents: busy || flags === null ? "none" : "auto" }}>
              <Tabs small label="Presets" value={activePreset}
                items={PRESETS.map(p => ({ key: p.key, label: p.label, title: p.desc }))}
                onChange={applyPreset} />
            </div>
          </div>

          {/* Per-flag toggles */}
          <div style={{
            fontSize: T.textXs, color: T.text4, fontFamily: T.mono,
            fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase",
            marginBottom: 6,
          }}>
            Features
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {FLAG_META.map(f => {
              const checked = flags?.[f.key] ?? false;
              return (
                <div
                  key={f.key}
                  style={{
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                    padding: "8px 10px",
                    borderRadius: 8,
                    background: T.overlay02,
                    border: `1px solid ${T.overlay06}`,
                    gap: 10,
                  }}
                >
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{
                      fontSize: T.textSm, color: T.text1,
                      fontFamily: T.font, fontWeight: 600,
                      marginBottom: 2,
                    }}>
                      {f.label}
                    </div>
                    <div style={{
                      fontSize: T.textXs, color: T.text4, fontFamily: T.font,
                      lineHeight: 1.35,
                    }}>
                      {f.desc}
                    </div>
                  </div>
                  <ToggleSwitch
                    checked={checked}
                    onChange={() => updateFlag(f.key, !checked)}
                  />
                </div>
              );
            })}
          </div>

          {/* Footer hint */}
          <div style={{
            marginTop: 12, paddingTop: 10,
            borderTop: `1px solid ${T.overlay06}`,
            fontSize: T.textXs, color: T.text4, fontFamily: T.mono,
            lineHeight: 1.5,
          }}>
            Toggles persist on disk. Background loops pick up changes within ~30s — no redeploy needed.
          </div>
        </div>
      )}
    </div>
  );
}
