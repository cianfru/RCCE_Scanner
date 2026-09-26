import { notificationDigest } from "../utils/notificationDigest.js";
import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { T, getBaseSymbol } from "../theme";
import TokenLogo from "./TokenLogo.jsx";
import { useWallet } from "../WalletContext.jsx";
import { useSharedWorker } from "../hooks/useSharedWorker.js";
import { useWebSocket } from "../hooks/useWebSocket.js";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const DISMISSED_KEY = "rcce-bell-dismissed";
const DISMISS_TTL_MS = 4 * 60 * 60 * 1000; // 4 hours

function getDismissed() {
  try {
    const raw = localStorage.getItem(DISMISSED_KEY);
    if (!raw) return [];
    const entries = JSON.parse(raw);
    // Prune expired entries
    const now = Date.now();
    const valid = entries.filter((e) => now - e.ts < DISMISS_TTL_MS);
    if (valid.length !== entries.length) {
      localStorage.setItem(DISMISSED_KEY, JSON.stringify(valid));
    }
    return valid;
  } catch { return []; }
}

function saveDismissed(list) {
  localStorage.setItem(DISMISSED_KEY, JSON.stringify(list));
}

function addDismissKeys(prev, keys) {
  const now = Date.now();
  const existing = new Set(prev.map((e) => e.key));
  const novel = keys.filter((k) => !existing.has(k)).map((k) => ({ key: k, ts: now }));
  return [...prev, ...novel];
}

function timeAgo(ts) {
  const diff = Math.floor(Date.now() / 1000) - ts;
  if (diff < 60) return "now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return `${Math.floor(diff / 86400)}d`;
}

export default function NotificationBell() {
  const navigate = useNavigate();
  const { address: walletAddress } = useWallet();
  const sw = useSharedWorker();
  const [anomalies, setAnomalies] = useState([]);
  const [warnings, setWarnings] = useState([]);
  const [exhaustionOpps, setExhaustionOpps] = useState([]);
  const [marketSetups, setMarketSetups] = useState([]);
  const [insights, setInsights] = useState([]);
  const [convergence, setConvergence] = useState([]);
  const [open, setOpen] = useState(false);
  const [dismissed, setDismissedState] = useState(getDismissed);
  const panelRef = useRef(null);

  // --- Dismiss helpers (localStorage with 4h TTL) ---
  const dismiss = (key) => {
    const next = addDismissKeys(dismissed, [key]);
    setDismissedState(next);
    saveDismissed(next);
  };

  const dismissMany = (keys) => {
    const next = addDismissKeys(dismissed, keys);
    setDismissedState(next);
    saveDismissed(next);
  };

  const clearAll = () => {
    const allKeys = [
      ...anomalies.map(a => `anom:${a.dedup_key}`),
      ...warnings.map(w => `warn:${w.type}:${w.symbol}`),
      ...exhaustionOpps.map(o => `opp:${o.type}:${o.symbol}`),
      ...marketSetups.map(s => `setup:${s.type}:${s.symbol}`),
      ...insights.map(i => i.key),
    ];
    dismissMany(allKeys);
  };


  const setupFilter = "HIGH";
  const [showAll, setShowAll] = useState(false);
  const [openGroup, setOpenGroup] = useState(null);     // group whose supporting updates are expanded

  // ── SharedWorker integration ──────────────────────────────────────────────

  // Forward wallet address to worker
  useEffect(() => {
    if (sw.supported) sw.setWallet(walletAddress || "");
  }, [sw.supported, sw.setWallet, walletAddress]);

  // Forward setupFilter to worker
  useEffect(() => {
    if (sw.supported) {
      const score = setupFilter === "HIGH" ? 3 : setupFilter === "MED" ? 2 : 0;
      sw.setNotifParams(score);
    }
  }, [sw.supported, sw.setNotifParams, setupFilter]);

  // Apply worker notif-data updates
  useEffect(() => {
    if (!sw.supported || !sw.notifData) return;
    const d = sw.notifData;
    setAnomalies(d.anomalies || []);
    setWarnings(d.warnings || []);
    setExhaustionOpps(d.exhaustionOpps || []);
    setMarketSetups(d.marketSetups || []);
  }, [sw.supported, sw.notifData]);

  // ── WebSocket real-time anomalies (instant push, no polling delay) ──────────

  const wsRef = useWebSocket();

  // Merge WebSocket anomalies as they arrive
  useEffect(() => {
    if (!wsRef.connected || !wsRef.anomalies || wsRef.anomalies.length === 0) return;
    setAnomalies((prev) => {
      const existingKeys = new Set(prev.map((a) => a.dedup_key));
      const novel = wsRef.anomalies.filter((a) => a.dedup_key && !existingKeys.has(a.dedup_key));
      return [...novel, ...prev];
    });
  }, [wsRef.connected, wsRef.anomalies]);

  // Capture proactive assistant insights
  useEffect(() => {
    if (!wsRef.insight) return;
    const key = `insight:${Math.floor(wsRef.insight.timestamp)}`;
    setInsights((prev) => {
      if (prev.some((i) => i.key === key)) return prev;
      return [{ ...wsRef.insight, key }, ...prev].slice(0, 10);
    });
  }, [wsRef.insight]);

  // ── Fallback data fetching (when SharedWorker unavailable) ────────────────

  const fetchAnomalies = useCallback(async () => {
    if (sw.supported) return;
    try {
      const res = await fetch(`${API_BASE}/api/notifications/anomalies`);
      if (!res.ok) return;
      const data = await res.json();
      setAnomalies(data.anomalies || []);
    } catch (_) {}
  }, [sw.supported]);

  const fetchWarnings = useCallback(async () => {
    if (sw.supported) return;
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
  }, [walletAddress, sw.supported]);

  const fetchExhaustionOpps = useCallback(async () => {
    if (sw.supported) return;
    try {
      const url = walletAddress
        ? `${API_BASE}/api/notifications/exhaustion-opportunities?address=${walletAddress}`
        : `${API_BASE}/api/notifications/exhaustion-opportunities`;
      const res = await fetch(url);
      if (!res.ok) return;
      const data = await res.json();
      setExhaustionOpps(data.opportunities || []);
    } catch (_) {}
  }, [walletAddress, sw.supported]);

  const fetchMarketSetups = useCallback(async () => {
    if (sw.supported) return;
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
  }, [walletAddress, setupFilter, sw.supported]);

  // Profitable traders converging on a coin: found once per wallet sweep (~30 min), polled directly
  useEffect(() => {
    const load = () => fetch(`${API_BASE}/api/notifications/convergence`)
      .then(r => (r.ok ? r.json() : null)).then(d => d && setConvergence(d.items || [])).catch(() => {});
    load();
    const iv = setInterval(load, 300_000);
    return () => clearInterval(iv);
  }, []);

  // Fallback polling — only runs when SharedWorker unavailable
  useEffect(() => {
    if (sw.supported) return;
    fetchAnomalies();
    fetchWarnings();
    fetchExhaustionOpps();
    fetchMarketSetups();
    const iv = setInterval(() => {
      fetchAnomalies(); fetchWarnings(); fetchExhaustionOpps(); fetchMarketSetups();
    }, 60_000);
    return () => clearInterval(iv);
  }, [sw.supported, fetchAnomalies, fetchWarnings, fetchExhaustionOpps, fetchMarketSetups]);

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
  const digest = notificationDigest({warnings, anomalies, setups:marketSetups, opportunities:exhaustionOpps, insights, convergence}, new Set(dismissed.map(x=>x.key)));
  const shown = showAll ? digest : digest.slice(0, 8);
  const important = shown.filter(g => g.priority < 10);        // position risks and critical market changes
  const more = shown.filter(g => g.priority >= 10);
  const goToCoin = symbol => {
    setOpen(false);
    navigate(`/scanner/${encodeURIComponent(symbol)}`);
  };
  const row = group => {
    const base = group.symbol ? getBaseSymbol(group.symbol) : null;
    const ago = group.timestamp > 0 ? (timeAgo(group.timestamp) === "now" ? "Just now" : `${timeAgo(group.timestamp)} ago`) : null;
    const summary = group.entries[0].summary;
    const expanded = openGroup === group.key;
    const title = group.title.charAt(0).toUpperCase() + group.title.slice(1);
    return <li key={group.key} className="notif-row" data-severity={group.severity || undefined}>
      <button type="button" className="notif-main" disabled={!group.symbol} onClick={() => group.symbol && goToCoin(group.symbol)}
        aria-label={`${base ? `${base}: ` : ""}${title}. ${summary}${group.symbol ? ". Open the coin page" : ""}`}>
        <span className="notif-logo" aria-hidden="true">
          {base ? <TokenLogo symbol={group.symbol.includes("/") ? group.symbol : `${base}/USDT`} size={36} /> : <span className="notif-logo-fallback">{group.category.charAt(0)}</span>}
        </span>
        <span className="notif-text">
          <span className="notif-title">{base && <b>{base}</b>}{base ? " · " : ""}{title}</span>
          <span className="notif-summary">{summary}</span>
          <span className="notif-meta">{group.category}{ago ? ` · ${ago}` : ""}</span>
        </span>
      </button>
      <button type="button" className="notif-dismiss" onClick={() => dismissMany(group.keys)} aria-label={`Dismiss ${base || title}`} title="Dismiss">
        <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true"><path d="M3 3l6 6M9 3l-6 6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /></svg>
      </button>
      {group.entries.length > 1 && <button type="button" className="notif-updates" aria-expanded={expanded}
        onClick={() => setOpenGroup(expanded ? null : group.key)}>{expanded ? "Hide updates" : `${group.entries.length} updates`}</button>}
      {expanded && <ul className="notif-entries">{group.entries.map((entry, i) => <li key={entry.key + i}>{entry.text}</li>)}</ul>}
    </li>;
  };
  return <div ref={panelRef} className="notification-digest">
    <button className="notification-trigger" aria-label={`Notifications, ${digest.length} updates`} aria-expanded={open} onClick={()=>setOpen(!open)}>
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M10 21h4"/></svg>
      {digest.length > 0 && <span>{digest.length}</span>}
    </button>
    {open && <section className="notification-panel" aria-label="Notifications" onKeyDown={e=>{if(e.key==='Escape')setOpen(false)}}>
      <header className="notif-head">
        <h2>Notifications</h2>
        {digest.length > 0 && <button type="button" onClick={clearAll}>Dismiss all</button>}
      </header>
      {important.length > 0 && <><h3 className="notif-section">Needs attention</h3><ul className="notif-list">{important.map(row)}</ul></>}
      {more.length > 0 && <><h3 className="notif-section">{important.length ? "More updates" : "Updates"}</h3><ul className="notif-list">{more.map(row)}</ul></>}
      {!digest.length && <p className="notif-empty">Nothing needs your attention right now.</p>}
      {digest.length > 8 && <button type="button" className="notif-more" onClick={()=>setShowAll(!showAll)}>{showAll ? "Show fewer" : `Show all ${digest.length}`}</button>}
    </section>}
  </div>;
}
