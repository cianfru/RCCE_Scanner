/**
 * SettingsDropdown — runtime feature toggles + presets.
 *
 * Renders a gear icon in the header. Click → popover with:
 *   - Appearance (Dark | Light)
 *   - Admin key, power state (Keep awake), presets (Idle / Normal / Power)
 *   - Per-feature On/Off
 * `embedded` renders the same form inline, for the /settings page.
 *
 * Reads/writes /api/admin/features. Toggles persist on disk and take
 * effect within ~30s without redeploy. Designed for the user's flow:
 *   - "Idle" when not actively trading (only core scanner runs)
 *   - "Normal" sentiment-mode default
 *   - "Power" HyperLens, on-chain tracker and monitor (order-book polling stays off: no page shows it)
 */
import { useState, useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { T } from "../theme.js";
import { useTheme } from "../ThemeContext";
import Tabs from "./Tabs.jsx";
import HelpTip from "./HelpTip.jsx";
import DataStatus from "./DataStatus.jsx";

import { getAdminKey, setAdminKey } from "../auth.js";
const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// Display metadata for each flag — order = display order in the panel.
const FLAG_META = [
  {
    key: "hyperlens_enabled",
    label: "Traders",
    desc: "Hyperliquid trader positioning (HyperLens)",
  },
  {
    key: "whale_tracker",
    label: "On-chain transfer tracker",
    desc: "Etherscan/BSCscan/Solscan polling every 2 min",
  },
  {
    key: "market_monitor",
    label: "Market monitor",
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

const THEMES = [{ key: "dark", label: "Dark" }, { key: "light", label: "Light" }];

// Section labels: sentence case, Geist 12/600, text3.
const SECTION = { fontSize: 12, fontWeight: 600, color: T.text3, fontFamily: T.font, letterSpacing: 0 };
const ROW = {
  display: "flex", alignItems: "center", justifyContent: "space-between",
  padding: "8px 10px",
  borderRadius: 8,
  background: T.overlay02,
  border: `1px solid ${T.overlay06}`,
  gap: 10,
};
const PERSIST = "Changes are saved on the server and picked up by the background loops within about 30 seconds. No redeploy is needed.";

// Flat text on/off control: no pill switch.
function ToggleSwitch({ checked, onChange, color = T.accent, disabled = false, label }) {
  return (
    <button
      type="button"
      onClick={onChange}
      disabled={disabled}
      aria-label={label}
      aria-pressed={checked}
      style={{
        border: "none", background: "transparent", padding: 0,
        cursor: disabled ? "not-allowed" : "pointer", flexShrink: 0, minWidth: 24, textAlign: "right",
        fontSize: 12, fontFamily: T.font, fontWeight: 600,
        color: checked ? color : T.text4,
      }}
    >
      {checked ? "On" : "Off"}
    </button>
  );
}

export default function SettingsDropdown({ embedded = false }) {
  const { mode, toggle } = useTheme();
  const [open, setOpen] = useState(embedded);
  const [hasAdminKey, setHasAdminKey] = useState(() => Boolean(getAdminKey()));
  const [readError, setReadError] = useState(false);
  const [readAttempt, setReadAttempt] = useState(0);
  const [flags, setFlags] = useState(null);
  const [activity, setActivity] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const popoverRef = useRef(null);
  const buttonRef = useRef(null);

  // Opened from elsewhere: a rescan refused for lack of the admin key.
  useEffect(() => {
    if (embedded) return undefined;
    const onOpen = () => setOpen(true);
    window.addEventListener("reflex-open-settings", onOpen);
    return () => window.removeEventListener("reflex-open-settings", onOpen);
  }, [embedded]);

  // Load on first open (again after Retry)
  useEffect(() => {
    if (!open || flags !== null) return undefined;
    let alive = true;
    setReadError(false);
    fetch(`${API_BASE}/api/admin/features`)
      .then(r => { if (!r.ok) throw new Error("Unavailable"); return r.json(); })
      .then(j => {
        if (!alive) return;
        if (!j?.flags) throw new Error("Configuration unavailable");
        setFlags(j.flags);
        if (j.activity) setActivity(j.activity);
      })
      .catch(() => { if (alive) setReadError(true); });
    return () => { alive = false; };
  }, [open, flags, readAttempt]);

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

  // Close on Escape and on a pointer press outside (help tips open from inside stay allowed).
  useEffect(() => {
    if (!open || embedded) return undefined;
    const onDown = (e) => {
      if (popoverRef.current?.contains(e.target)) return;
      if (buttonRef.current?.contains(e.target)) return;
      if (e.target.closest?.(".alt-season-explanation")) return;
      setOpen(false);
    };
    const onKey = (e) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      buttonRef.current?.focus();
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("pointerdown", onDown); document.removeEventListener("keydown", onKey); };
  }, [open, embedded]);

  const updateFlag = async (key, value) => {
    if (busy) return;
    setBusy(true);
    setErr(null);
    // Optimistic update
    setFlags(prev => ({ ...(prev || {}), [key]: value }));
    const revert = () => {
      setFlags(prev => ({ ...(prev || {}), [key]: !value }));
      setErr("Not saved");
    };
    try {
      const res = await fetch(`${API_BASE}/api/admin/features`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ flags: { [key]: value } }),
      });
      if (res.ok) {
        const j = await res.json();
        if (j.flags) setFlags(j.flags);
      } else {
        revert();
      }
    } catch {
      revert();
    } finally {
      setBusy(false);
    }
  };

  const applyPreset = async (preset) => {
    if (busy) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch(`${API_BASE}/api/admin/features`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preset }),
      });
      if (res.ok) {
        const j = await res.json();
        if (j.flags) setFlags(j.flags);
      } else {
        setErr("Preset not applied");
      }
    } catch {
      setErr("Preset not applied");
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

  // The settings page is read-only until an admin key is entered; the popover keeps today's behaviour.
  const readOnly = embedded && !hasAdminKey;

  const panelStyle = embedded
    ? { position: "relative", width: "100%" }
    : {
        position: "absolute",
        top: "calc(100% + 8px)",
        right: 0,
        width: 320,
        maxWidth: "calc(100vw - 32px)",
        maxHeight: "calc(100dvh - var(--header-offset) - var(--tabbar-space) - 20px)",
        overflowY: "auto",
        overscrollBehavior: "contain",
        backgroundColor: "var(--t-bg)",
        backgroundImage: "var(--t-popoverBg)",
        border: `1px solid ${T.border}`,
        borderRadius: 12,
        boxShadow: "0 12px 40px rgba(0,0,0,0.6)",
        zIndex: 100,
        padding: 14,
        textAlign: "left",
      };

  return (
    <div style={{ position: "relative" }}>
      {!embedded && <button
        ref={buttonRef}
        type="button"
        className="header-gear"
        onClick={() => setOpen(o => !o)}
        title="Settings"
        aria-label="Settings"
        aria-expanded={open}
        aria-haspopup="dialog"
        style={{
          width: 30, height: 30,
          padding: 0,
          display: "flex", alignItems: "center", justifyContent: "center",
          background: open ? T.overlay06 : "transparent",
          // Borderless while closed, like refresh and the bell, on the metal plate (metal_rules.md).
          // Owner decision (g), spec section 10: today's closed gear has a 1px T.border ring. If the
          // owner keeps it, swap "transparent" for T.border here; the gear sits outside the sheen and grain.
          border: `1px solid ${open ? T.accent : "transparent"}`,
          borderRadius: 8,
          color: open ? T.accent : T.text3,
          cursor: "pointer",
          transition: "all 0.15s",
        }}
        onMouseEnter={e => { if (!open) e.currentTarget.style.color = T.text1; }}
        onMouseLeave={e => { if (!open) e.currentTarget.style.color = T.text3; }}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      </button>}

      {open && (
        <div
          ref={popoverRef}
          className={embedded ? "settings-form" : "settings-popover"}
          role={embedded ? undefined : "dialog"}
          aria-label={embedded ? undefined : "Settings"}
          style={panelStyle}
        >
          {/* Header */}
          {!embedded && <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            marginBottom: 10, paddingBottom: 8,
            borderBottom: `1px solid ${T.overlay06}`,
          }}>
            <span style={{ fontSize: T.textSm, color: T.text1, fontFamily: T.font, fontWeight: 600 }}>
              Runtime settings
            </span>
          </div>}

          {/* Appearance */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, marginBottom: 10 }}>
            <span style={SECTION}>Appearance</span>
            <Tabs small label="Appearance" items={THEMES} value={mode} onChange={k => { if (k !== mode) toggle(); }} />
          </div>

          <DataStatus label="Runtime configuration" loading={!flags && !readError} error={readError}
            onRetry={() => { setReadError(false); setReadAttempt(n => n + 1); }} />

          {/* Admin key: needed for changes once REFLEX_ADMIN_KEY is set on the server */}
          <label style={{ display: "block", marginBottom: 14 }}>
            <span style={{ display: "block", fontSize: 12, color: T.text3, fontFamily: T.font, marginBottom: 6 }}>
              Admin key <span style={{ color: T.text4 }}>(for changes; stored in this browser only)</span>
            </span>
            <input type="password" autoComplete="off" defaultValue={getAdminKey()} placeholder="Not set"
              onChange={e => { setAdminKey(e.target.value); setHasAdminKey(Boolean(e.target.value.trim())); }}
              style={{ width: "100%", boxSizing: "border-box", height: 34, padding: "0 10px", borderRadius: 6,
                border: `1px solid ${T.border}`, background: T.overlay04, color: T.text1, fontFamily: T.mono, fontSize: 12 }} />
          </label>

          <fieldset disabled={readOnly} aria-label="Server controls" style={{ border: 0, margin: 0, padding: 0, minWidth: 0 }}>
          {readOnly && <p style={{ margin: "0 0 12px", fontSize: 12, color: T.text3, fontFamily: T.font }}>Read-only. Enter the admin key above to change these.</p>}

          {/* Power state — active/idle throttle */}
          <div style={{ marginBottom: 14 }}>
            <div style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              marginBottom: 6,
            }}>
              <span style={SECTION}>Power state</span>
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
            <div style={ROW}>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{
                  fontSize: T.textSm, color: T.text1,
                  fontFamily: T.font, fontWeight: 600, marginBottom: 2,
                }}>
                  Keep awake
                </div>
                <div style={{
                  fontSize: T.textXs, color: T.text4, fontFamily: T.font, lineHeight: 1.35,
                }}>
                  Pin full-speed scanning on. Off: auto-idle when no dashboard is open (wakes instantly on reload).
                </div>
              </div>
              <ToggleSwitch
                label="Keep scanning awake"
                disabled={busy || readOnly}
                checked={flags?.keep_active ?? false}
                color={T.green}
                onChange={() => updateFlag("keep_active", !(flags?.keep_active ?? false))}
              />
            </div>
          </div>

          {/* Presets */}
          <div style={{ marginBottom: 14 }}>
            <div style={{ ...SECTION, display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
              Presets
              <HelpTip title="Presets" width={280}>
                <p>Idle: the scanner only, every other feature off. Normal: the default. Power: everything on.</p>
                <p>{PERSIST}</p>
              </HelpTip>
            </div>
            <div style={{ opacity: flags === null ? 0.5 : 1, pointerEvents: busy || flags === null || readOnly ? "none" : "auto" }}>
              <Tabs small label="Presets" value={activePreset}
                items={PRESETS.map(p => ({ key: p.key, label: p.label, title: p.desc }))}
                onChange={applyPreset} />
            </div>
          </div>

          {/* Per-flag toggles */}
          <div style={{ ...SECTION, display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
            Features
            <HelpTip title="Features" width={280}><p>{PERSIST}</p></HelpTip>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {FLAG_META.map(f => {
              const checked = flags?.[f.key] ?? false;
              return (
                <div key={f.key} style={ROW}>
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
                    label={f.label}
                    disabled={busy || readOnly}
                    checked={checked}
                    onChange={() => updateFlag(f.key, !checked)}
                  />
                </div>
              );
            })}
          </div>
          </fieldset>

          {err && (
            <div style={{ marginTop: 10, fontSize: 12, color: T.red, fontFamily: T.font }}>
              {err}
            </div>
          )}

          {!embedded && (
            <div style={{ marginTop: 12, paddingTop: 10, borderTop: `1px solid ${T.overlay06}` }}>
              <Link className="te-link" to="/settings" onClick={() => setOpen(false)}>Open settings page</Link>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
