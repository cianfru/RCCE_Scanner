import { useEffect, useState } from "react";
import { SEEN_KEY, getStorage, markHistorySeen, showHistoryDot } from "../utils/marketSpark.js";

// The one-time dot on the Market consensus card's history button. Every button that opens the Market history
// drawer calls noteHistoryOpened, so the dot goes away for good also when the drawer was opened from the
// Fear & Greed dial, and in other open tabs (storage event).
const listeners = new Set();
let seenThisTab = false;

export function noteHistoryOpened() {
  seenThisTab = true;
  markHistorySeen(getStorage());
  listeners.forEach(fn => fn());
}

export default function useHistoryDot() {
  const [dot, setDot] = useState(() => !seenThisTab && showHistoryDot(getStorage()));
  useEffect(() => {
    const off = () => setDot(false);
    const onStorage = e => { if (e.key === SEEN_KEY) off(); };
    listeners.add(off);
    window.addEventListener("storage", onStorage);
    return () => { listeners.delete(off); window.removeEventListener("storage", onStorage); };
  }, []);
  return dot;
}
