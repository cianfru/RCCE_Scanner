// One shared feed for the landing (hero card and scanner preview): fetched once on
// open, then every five minutes while the tab is visible. The server answers an
// unchanged snapshot with an empty 304 (ETag), so a refresh usually costs nothing.
import { useEffect, useState } from "react";
import { previewRows, PREVIEW_REFRESH_MS } from "../utils/previewRows.js";
import { pollWhileVisible } from "../utils/visiblePoll.js";

const API_BASE = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

let state = { rows: [], loading: true, error: "", updated: null };
const subscribers = new Set();
let stop = null;
let inflight = null;

function emit(next) {
  state = { ...state, ...next };
  for (const fn of subscribers) fn(state);
}

async function refresh() {
  if (inflight) return inflight;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12000);
  inflight = (async () => {
    try {
      const response = await fetch(`${API_BASE}/api/public/preview?timeframe=1d`, { signal: controller.signal });
      if (!response.ok) throw new Error("Scanner unavailable");
      const data = await response.json();
      if (!Array.isArray(data.results)) throw new Error("Invalid scan response");
      emit({ rows: previewRows(data.results), loading: false, error: "", updated: new Date() });
    } catch {
      emit({ loading: false, error: "The scanner feed is temporarily unavailable." });
    } finally {
      clearTimeout(timeout);
      inflight = null;
    }
  })();
  return inflight;
}

function subscribe(fn) {
  subscribers.add(fn);
  if (!stop) {
    if (!state.updated) refresh();
    stop = pollWhileVisible(refresh, PREVIEW_REFRESH_MS);
  }
  fn(state);
  return () => {
    subscribers.delete(fn);
    if (subscribers.size === 0 && stop) { stop(); stop = null; }
  };
}

export function usePreviewFeed() {
  const [feed, setFeed] = useState(state);
  useEffect(() => subscribe(setFeed), []);
  return feed;
}
