/**
 * SettingsForm — runtime feature toggles + presets, for the owner's /settings page:
 *   - Appearance (Dark | Light)
 *   - Admin key, power state (Keep awake), presets (Idle / Normal / Power)
 *   - Per-feature On/Off
 *
 * Reads/writes /api/admin/features. Toggles persist on disk and take
 * effect within ~30s without redeploy. Designed for the user's flow:
 *   - "Idle" when not actively trading (only core scanner runs)
 *   - "Normal" sentiment-mode default
 *   - "Power" HyperLens, on-chain tracker and monitor (order-book polling stays off: no page shows it)
 */
import { useState, useEffect } from "react";
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
    desc: "Hyperliquid trader positioning",
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

// Flat text on/off control: no pill switch. checked === null while the flags load: a dash, not "Off".
function ToggleSwitch({ checked, onChange, color = T.accent, disabled = false, label }) {
  const unknown = checked === null;
  return (
    <button
      type="button"
      onClick={onChange}
      disabled={disabled || unknown}
      aria-label={unknown ? `${label}: loading` : label}
      aria-pressed={unknown ? undefined : checked}
      className="settings-toggle"
      style={{
        border: "none", background: "transparent", padding: 0, opacity: disabled ? 0.55 : 1,
        cursor: disabled ? "not-allowed" : unknown ? "default" : "pointer", flexShrink: 0, minWidth: 24, textAlign: "right",
        fontSize: 12, fontFamily: T.font, fontWeight: 600,
        color: checked ? color : T.text4,
      }}
    >
      {unknown ? "\u2014" : checked ? "On" : "Off"}
    </button>
  );
}

export default function SettingsForm() {
  const { mode, toggle } = useTheme();
  const [hasAdminKey, setHasAdminKey] = useState(() => Boolean(getAdminKey()));
  const [readError, setReadError] = useState(false);
  const [readAttempt, setReadAttempt] = useState(0);
  const [flags, setFlags] = useState(null);
  const [activity, setActivity] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  // Load once (again after Retry)
  useEffect(() => {
    if (flags !== null) return undefined;
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
  }, [flags, readAttempt]);

  // Live activity badge — polled while the page is open. This endpoint is
  // excluded from activity tracking, so polling it never keeps the app awake.
  useEffect(() => {
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
  }, []);

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

  // Read-only until an admin key is entered.
  const readOnly = !hasAdminKey;

  return (
    <div className="settings-form" style={{ position: "relative", width: "100%" }}>
      {/* Appearance */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, marginBottom: 10 }}>
        <span style={SECTION}>Appearance</span>
        <div className="settings-tabs-end">
          <Tabs small label="Appearance" items={THEMES} value={mode} onChange={k => { if (k !== mode) toggle(); }} />
        </div>
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

      <fieldset className="settings-server" disabled={readOnly} aria-label="Server controls" style={{ border: 0, margin: 0, padding: 0, minWidth: 0 }}>
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
                fontSize: T.textXs, fontFamily: T.mono, fontWeight: 700,
                letterSpacing: "0.06em", color,
              }}>
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
            checked={flags ? (flags.keep_active ?? false) : null}
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
        <div className="settings-tabs-start" style={{ opacity: flags === null ? 0.5 : 1, pointerEvents: busy || flags === null ? "none" : "auto" }}>
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
          const checked = flags ? (flags[f.key] ?? false) : null;
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
    </div>
  );
}
