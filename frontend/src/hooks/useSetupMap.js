import { useCallback, useEffect, useState } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const REFRESH_MS = 300_000;

// The setup map for one timeframe (refreshed every five minutes while the page is
// visible), the watch list, and optionally the positions to mark as "mine".
export default function useSetupMap(tf, mineAddress, mineOn) {
  const [data, setData] = useState(null);
  const [watch, setWatch] = useState(null);
  const [mine, setMine] = useState(null);
  useEffect(() => {
    let alive = true;
    const load = () => fetch(`${API_BASE}/api/setup-map?tf=${tf}`).then(r => (r.ok ? r.json() : null))
      .then(d => { if (alive && d) setData(d); }).catch(() => {});
    setData(null);
    load();
    const timer = setInterval(() => { if (!document.hidden) load(); }, REFRESH_MS);
    return () => { alive = false; clearInterval(timer); };
  }, [tf]);
  const loadWatch = useCallback(() => fetch(`${API_BASE}/api/setup-map/watch`).then(r => (r.ok ? r.json() : null))
    .then(d => d && setWatch(d)).catch(() => {}), []);
  useEffect(() => { loadWatch(); }, [loadWatch]);
  useEffect(() => {
    if (!mineOn) { setMine(null); return undefined; }
    let alive = true;
    const q = mineAddress ? `?address=${encodeURIComponent(mineAddress)}` : "";
    fetch(`${API_BASE}/api/setup-map/mine${q}`).then(r => (r.ok ? r.json() : null))
      .then(d => { if (alive) setMine(d); }).catch(() => {});
    return () => { alive = false; };
  }, [mineOn, mineAddress]);
  const watched = new Set((watch?.coins || []).map(c => c.coin));
  // Changes need the admin key; the global fetch wrapper adds it.
  const toggleWatch = useCallback(async coin => {
    const on = watched.has(coin);
    const res = await fetch(`${API_BASE}/api/setup-map/watch${on ? `/${encodeURIComponent(coin)}` : ""}`, on
      ? { method: "DELETE" }
      : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ coin, tf }) });
    if (res.ok) await loadWatch();
    return res.ok;
  }, [watched, loadWatch, tf]);
  return { data, watched, telegram: watch?.telegram, toggleWatch, mine: mine?.positions || null };
}
